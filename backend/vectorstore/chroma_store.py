"""ChromaDB·Google Gemini 임베딩을 사용하는 테이블 스키마 벡터 저장소입니다."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Literal

import chromadb
from chromadb.api.models.Collection import Collection
from google import genai

from dataclasses import replace

from backend.config import Settings, get_settings
from backend.models import ColumnSchema, SearchResult, TableSchema
from backend.schema_naming import (
    canonical_pool_table_name,
    canonicalize_fk_reference,
)

logger = logging.getLogger(__name__)

SchemaPool = Literal["customer", "admin"]

# `get_table` 폴백용(고객 풀 데모 샘플). 패키지 루트 = backend/ 상위.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SAMPLE_CUSTOMER_XLSX_DIR = _REPO_ROOT / "data" / "excel" / "sample_customer"
_SAMPLE_ADMIN_XLSX_DIR = _REPO_ROOT / "data" / "excel" / "sample_admin"
# 메타(columns_json)가 예전 버전일 때 샘플 엑셀로 덮어쓸지 판단합니다.
_CUSTOMER_DEMO_REQUIRED_COLS: dict[str, frozenset[str]] = {
    "TBL_CUSTDIM": frozenset({"GENDER_CD"}),
    "TBL_SALEFACT": frozenset({"PROD_ID", "SALE_QTY"}),
    "TBL_EMPDIM": frozenset({"JOB_GRADE", "ANNUAL_SAL"}),
}
_ADMIN_DEMO_REQUIRED_COLS: dict[str, frozenset[str]] = {
    "TB_PRODUCTDIM": frozenset({"CAT_NM", "CAT_CD"}),
    "TB_SALEFACT": frozenset({"SALE_QTY", "PROD_ID"}),
    "TB_BUDGETFACT": frozenset({"BGT_AMT", "ACT_AMT"}),
    "TB_CUSTDIM": frozenset({"REG_DT"}),
}

# Chroma 메타데이터에는 None 이 허용되지 않습니다(값은 str/int/float/bool 만).
_META_STR_MAX = 8000
_META_DESC_MAX = 4000
_COLUMNS_JSON_MAX = 120000

_EMBED_BATCH_SIZE = 100
_EMBED_RETRY_DELAYS_SEC = (1.0, 2.0, 4.0)


def _nz_str(value: Any, max_len: int = _META_STR_MAX) -> str:
    """None·개행을 제거한 문자열(Chroma 메타용)."""
    if value is None:
        return ""
    s = str(value).replace("\r", " ").replace("\n", " ").strip()
    return s[:max_len]


def _schema_with_canonical_names(s: TableSchema) -> TableSchema:
    """인덱싱·ID 일치용으로 테이블명·FK 참조 테이블 부분을 규칙에 맞게 통일합니다."""
    cols: list[ColumnSchema] = []
    for c in s.columns:
        fk = c.fk_reference
        if (fk or "").strip():
            fk = canonicalize_fk_reference(fk)
        cols.append(replace(c, fk_reference=fk))
    return replace(
        s,
        table_name=canonical_pool_table_name(s.table_name),
        columns=cols,
    )


def _parse_file_schema_for_table(path: Path, canon_name: str) -> TableSchema:
    """엑셀을 파싱해 `canon_name`에 해당하는 테이블 스키마 한 건을 고릅니다(복수 테이블 파일 지원)."""
    from backend.parser.excel_parser import parse_file

    want = canonical_pool_table_name(canon_name.upper())
    lst = [_schema_with_canonical_names(p) for p in parse_file(path)]
    for p in lst:
        if p.table_name == want:
            return p
    if len(lst) == 1:
        return lst[0]
    raise ValueError(f"{path.name}에 테이블 {want} 정의를 찾지 못했습니다.")


def _metadata_for_schema(
    s: TableSchema, *, include_columns_json: bool = True
) -> dict[str, Any]:
    """Chroma upsert용 메타데이터. None 값을 넣지 않습니다."""
    pk_cols = ",".join(c.name for c in s.columns if c.is_pk)
    meta: dict[str, Any] = {
        "table_name": _nz_str(s.table_name, 256),
        "korean_name": _nz_str(s.korean_name),
        "domain": _nz_str(s.domain),
        "column_count": int(len(s.columns)),
        "pk_columns": _nz_str(pk_cols),
        "source_file": _nz_str(s.source_file),
        "table_description": _nz_str(s.description, _META_DESC_MAX),
    }
    if include_columns_json:
        cj = _columns_to_json_str(s.columns)
        if len(cj) > _COLUMNS_JSON_MAX:
            logger.warning(
                "columns_json이 너무 커 생략합니다: %s (%s bytes)",
                s.table_name,
                len(cj),
            )
        else:
            meta["columns_json"] = cj
    return meta


def _columns_to_json_str(columns: list[ColumnSchema]) -> str:
    """Chroma 메타데이터에 넣기 위해 컬럼 목록을 JSON 문자열로 직렬화합니다."""
    payload = [
        {
            "name": c.name,
            "korean_name": c.korean_name,
            "data_type": c.data_type,
            "is_pk": c.is_pk,
            "is_fk": c.is_fk,
            "fk_reference": c.fk_reference,
            "nullable": c.nullable,
            "description": c.description,
            "is_indexed": c.is_indexed,
        }
        for c in columns
    ]
    return json.dumps(payload, ensure_ascii=False)


def _columns_from_metadata(meta: dict[str, Any]) -> list[ColumnSchema]:
    """메타데이터의 columns_json에서 ColumnSchema 목록을 복원합니다."""
    raw = meta.get("columns_json")
    if not raw:
        return []
    try:
        if isinstance(raw, str):
            arr = json.loads(raw)
        else:
            arr = raw
        if not isinstance(arr, list):
            return []
        out: list[ColumnSchema] = []
        for d in arr:
            if not isinstance(d, dict):
                continue
            fk_ref = str(d.get("fk_reference", ""))
            if fk_ref.strip():
                fk_ref = canonicalize_fk_reference(fk_ref)
            out.append(
                ColumnSchema(
                    name=str(d.get("name", "")),
                    korean_name=str(d.get("korean_name", "")),
                    data_type=str(d.get("data_type", "")),
                    is_pk=bool(d.get("is_pk")),
                    is_fk=bool(d.get("is_fk")),
                    fk_reference=fk_ref,
                    nullable=bool(d.get("nullable")),
                    description=str(d.get("description", "")),
                    is_indexed=bool(d.get("is_indexed")),
                )
            )
        return out
    except (json.JSONDecodeError, TypeError, KeyError) as exc:
        logger.warning("columns_json 복원 실패: %s", exc)
        return []


class SchemaVectorStore:
    """테이블 스키마 청크를 임베딩하여 ChromaDB에 저장하고 검색합니다."""

    def __init__(self) -> None:
        self._settings: Settings = get_settings()
        self.genai_client = genai.Client(api_key=self._settings.GOOGLE_API_KEY)
        self.embed_model = self._settings.EMBEDDING_MODEL
        self._chroma = chromadb.PersistentClient(
            path=self._settings.CHROMA_PERSIST_DIR
        )
        self._collection_cache: dict[str, Collection] = {}

    def _collection_name(self, pool: SchemaPool) -> str:
        if pool == "customer":
            return self._settings.customer_collection_name()
        return self._settings.CHROMA_COLLECTION_ADMIN

    def _get_collection(self, pool: SchemaPool) -> Collection:
        name = self._collection_name(pool)
        if name not in self._collection_cache:
            self._collection_cache[name] = self._chroma.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection_cache[name]

    def _recreate_collection(self, pool: SchemaPool) -> None:
        """지정 풀의 컬렉션을 삭제한 뒤 동일 이름으로 다시 만듭니다."""
        name = self._collection_name(pool)
        try:
            self._chroma.delete_collection(name)
        except Exception:
            logger.exception("컬렉션 삭제 중 오류(무시 가능)")
        self._collection_cache[name] = self._chroma.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    def _embed_one_with_retry(self, text: str) -> list[float]:
        """Gemini `embed_content`로 단일 텍스트 임베딩을 생성합니다. 실패 시 최대 3회 재시도합니다."""
        last_err: Exception | None = None
        for attempt in range(4):
            try:
                result = self.genai_client.models.embed_content(
                    model=self.embed_model,
                    contents=text,
                )
                vector = result.embeddings[0].values
                return list(vector) if vector is not None else []
            except Exception as exc:
                last_err = exc
                logger.warning(
                    "Gemini 임베딩 실패 (시도 %s/4): %s",
                    attempt + 1,
                    exc,
                )
                if attempt < 3:
                    time.sleep(_EMBED_RETRY_DELAYS_SEC[attempt])
        assert last_err is not None
        raise last_err

    def _embed_texts_with_retry(self, texts: list[str]) -> list[list[float]]:
        """여러 텍스트에 대해 순차적으로 임베딩을 생성합니다."""
        return [self._embed_one_with_retry(t) for t in texts]

    def index_schemas(
        self,
        schemas: list[TableSchema],
        reset: bool = False,
        *,
        schema_pool: SchemaPool = "customer",
    ) -> dict[str, Any]:
        """여러 TableSchema를 벡터 DB에 인덱싱합니다."""
        indexed = 0
        skipped = 0
        errors: list[str] = []
        coll = self._get_collection(schema_pool)

        if reset:
            self._recreate_collection(schema_pool)
            coll = self._get_collection(schema_pool)

        if not schemas:
            return {"indexed": indexed, "skipped": skipped, "errors": errors}

        raw_schemas: list[TableSchema] = []
        for s in schemas:
            if not (s.table_name or "").strip():
                skipped += 1
                errors.append("table_name이 비어 있어 건너뜀")
                continue
            raw_schemas.append(_schema_with_canonical_names(s))

        # Chroma id = table_name 이므로 동일 테이블명이 두 번 이상이면 upsert 단계에서 실패합니다.
        # 여러 .xlsx·멀티 시트 등으로 중복될 수 있어 마지막 정의만 유지합니다.
        by_table: dict[str, TableSchema] = {}
        for s in raw_schemas:
            by_table[s.table_name] = s
        n_dup = len(raw_schemas) - len(by_table)
        if n_dup > 0:
            logger.warning(
                "인덱싱 입력에 중복 table_name %s건 — 동일 이름은 마지막 스키마만 유지합니다.",
                n_dup,
            )
        to_process = sorted(
            by_table.values(), key=lambda x: x.table_name
        )

        for start in range(0, len(to_process), _EMBED_BATCH_SIZE):
            batch = to_process[start : start + _EMBED_BATCH_SIZE]
            texts = [s.to_chunk_text() for s in batch]
            try:
                embeddings = self._embed_texts_with_retry(texts)
            except Exception as exc:
                msg = f"임베딩 배치 실패(행 {start}~{start + len(batch) - 1}): {exc}"
                logger.exception(msg)
                errors.append(msg)
                skipped += len(batch)
                continue

            ids = [s.table_name for s in batch]
            metadatas = [_metadata_for_schema(s, include_columns_json=True) for s in batch]

            try:
                coll.upsert(
                    ids=ids,
                    documents=texts,
                    embeddings=embeddings,
                    metadatas=metadatas,
                )
                indexed += len(batch)
            except Exception as exc:
                logger.warning(
                    "Chroma upsert 실패(컬럼 JSON 제외 후 재시도): %s",
                    exc,
                )
                try:
                    metadatas_min = [
                        _metadata_for_schema(s, include_columns_json=False) for s in batch
                    ]
                    coll.upsert(
                        ids=ids,
                        documents=texts,
                        embeddings=embeddings,
                        metadatas=metadatas_min,
                    )
                    indexed += len(batch)
                    logger.info(
                        "컬럼 메타 없이 upsert 성공(행 %s~%s)",
                        start,
                        start + len(batch) - 1,
                    )
                except Exception as exc2:
                    msg = (
                        f"Chroma upsert 실패(행 {start}~{start + len(batch) - 1}): "
                        f"{exc2}"
                    )
                    logger.exception(msg)
                    errors.append(msg)
                    skipped += len(batch)

        return {"indexed": indexed, "skipped": skipped, "errors": errors}

    def search(
        self,
        query: str,
        top_k: int | None = None,
        domain: str | None = None,
        *,
        schema_pool: SchemaPool = "customer",
    ) -> list[SearchResult]:
        """자연어 쿼리로 관련 테이블을 검색합니다."""
        k = self._settings.TOP_K_RESULTS if top_k is None else top_k
        q_emb = self._embed_texts_with_retry([query])[0]
        coll = self._get_collection(schema_pool)

        query_kwargs: dict[str, Any] = {
            "query_embeddings": [q_emb],
            "n_results": k,
            "include": ["documents", "metadatas", "distances"],
        }
        if domain is not None:
            query_kwargs["where"] = {"domain": {"$eq": domain}}

        raw = coll.query(**query_kwargs)

        out: list[SearchResult] = []
        ids_list = raw.get("ids") or []
        docs_list = raw.get("documents") or []
        meta_list = raw.get("metadatas") or []
        dist_list = raw.get("distances") or []

        if not ids_list or not ids_list[0]:
            return out

        for i, _id in enumerate(ids_list[0]):
            doc = docs_list[0][i] if docs_list and docs_list[0] else ""
            meta = meta_list[0][i] if meta_list and meta_list[0] else {}
            dist = dist_list[0][i] if dist_list and dist_list[0] else 0.0
            d = float(dist) if dist is not None else 0.0
            score = float(1.0 - d)
            tn = (meta or {}).get("table_name", _id)
            canon_tn = canonical_pool_table_name(str(tn))
            out.append(
                SearchResult(
                    table_name=canon_tn,
                    score=score,
                    chunk_text=doc or "",
                    metadata=dict(meta or {}),
                )
            )
        return out

    def augment_search_replace_tables(
        self,
        results: list[SearchResult],
        tables: list[str],
        *,
        schema_pool: SchemaPool = "customer",
    ) -> list[SearchResult]:
        """지정 테이블은 벡터 검색 청크 대신 저장소의 최신 `TableSchema`로 넣습니다.

        오래된 임베딩 본문·누락된 상위 K건으로 인해 스키마가 빠지는 경우를 줄입니다.
        """
        to_inject: list[TableSchema] = []
        canons: set[str] = set()
        for name in tables:
            if not (name or "").strip():
                continue
            canon = canonical_pool_table_name(name.strip().upper())
            ts = self.get_table(canon, schema_pool=schema_pool)
            if ts is None:
                continue
            to_inject.append(ts)
            canons.add(canon)
        if not to_inject:
            return results

        filtered = [
            r
            for r in results
            if canonical_pool_table_name(r.table_name) not in canons
        ]
        injected = [
            SearchResult(
                table_name=ts.table_name,
                score=1.0,
                chunk_text=ts.to_chunk_text(),
                metadata={"source": "store_refresh"},
            )
            for ts in to_inject
        ]
        return injected + filtered

    def search_results_from_all_tables(
        self,
        *,
        schema_pool: SchemaPool,
        max_tables: int = 24,
    ) -> list[SearchResult]:
        """벡터 검색이 빈 경우, 풀에 있는 테이블 전체 스키마를 검색 결과 형태로 만듭니다."""
        rows = self.list_tables(domain=None, schema_pool=schema_pool)
        out: list[SearchResult] = []
        for row in rows[:max_tables]:
            tn = str(row.get("table_name", "") or "").strip()
            if not tn:
                continue
            ts = self.get_table(tn, schema_pool=schema_pool)
            if ts is None:
                continue
            out.append(
                SearchResult(
                    table_name=ts.table_name,
                    score=0.55,
                    chunk_text=ts.to_chunk_text(),
                    metadata={"source": "pool_fallback"},
                )
            )
        return out

    def _resolve_chroma_table_id(
        self, table_name: str, *, schema_pool: SchemaPool
    ) -> str | None:
        """Chroma 문서 id(레거시 밑줄 명 등)를 규칙에 맞는 이름으로 역추적합니다."""
        raw = (table_name or "").strip()
        if not raw:
            return None
        coll = self._get_collection(schema_pool)
        target = canonical_pool_table_name(raw.upper())

        for candidate in (raw, target):
            if not candidate:
                continue
            res = coll.get(ids=[candidate], include=[])
            if res.get("ids"):
                return str(res["ids"][0])

        try:
            n_docs = coll.count()
            if n_docs == 0:
                return None
            res = coll.get(limit=max(n_docs, 1), include=["metadatas"])
        except Exception:
            res = coll.get(include=["metadatas"])
        ids_list = list(res.get("ids") or [])
        metas_raw = res.get("metadatas") or []
        metas = (
            list(metas_raw)
            if metas_raw is not None
            else [None] * len(ids_list)
        )
        if len(metas) < len(ids_list):
            metas.extend([None] * (len(ids_list) - len(metas)))
        for i, tid in enumerate(ids_list):
            tid_s = str(tid)
            m = metas[i] if i < len(metas) else None
            meta_tn = ""
            if isinstance(m, dict):
                meta_tn = str(m.get("table_name", "")).strip()
            if canonical_pool_table_name(tid_s.upper()) == target:
                return tid_s
            if meta_tn and canonical_pool_table_name(meta_tn.upper()) == target:
                return tid_s
        return None

    def get_table(
        self, table_name: str, *, schema_pool: SchemaPool = "customer"
    ) -> TableSchema | None:
        """테이블명으로 직접 조회합니다."""
        resolved = self._resolve_chroma_table_id(
            table_name, schema_pool=schema_pool
        )
        if not resolved:
            return None

        coll = self._get_collection(schema_pool)
        res = coll.get(
            ids=[resolved],
            include=["documents", "metadatas"],
        )
        ids = res.get("ids") or []
        if not ids:
            return None

        docs = res.get("documents") or []
        metas = res.get("metadatas") or []
        chunk_text = docs[0] if docs else ""
        meta = metas[0] if metas else {}
        desc = str(meta.get("table_description", ""))
        if not desc.strip() and chunk_text:
            desc = str(chunk_text).split("\n")[0][:500]

        canon_name = canonical_pool_table_name(
            str(meta.get("table_name", resolved))
        )
        source_raw = str(meta.get("source_file", "") or "").strip()
        demo_path: Path | None = None
        if schema_pool == "customer":
            dp = _SAMPLE_CUSTOMER_XLSX_DIR / f"{canon_name}.xlsx"
            if dp.is_file():
                demo_path = dp
        elif schema_pool == "admin":
            dp = _SAMPLE_ADMIN_XLSX_DIR / f"{canon_name}.xlsx"
            if dp.is_file():
                demo_path = dp

        def _table_from_parsed(parsed: TableSchema) -> TableSchema:
            return TableSchema(
                table_name=canon_name,
                korean_name=parsed.korean_name,
                domain=parsed.domain,
                description=parsed.description or desc,
                source_file=parsed.source_file,
                columns=parsed.columns,
            )

        required: frozenset[str] | None = None
        if schema_pool == "customer":
            required = _CUSTOMER_DEMO_REQUIRED_COLS.get(canon_name)
        elif schema_pool == "admin":
            required = _ADMIN_DEMO_REQUIRED_COLS.get(canon_name)

        if source_raw:
            sp = Path(source_raw)
            if sp.is_file():
                try:
                    parsed_src = _parse_file_schema_for_table(sp, canon_name)
                    names = {c.name for c in parsed_src.columns}
                    if (
                        required
                        and demo_path is not None
                        and not required.issubset(names)
                        and sp.resolve() != demo_path.resolve()
                    ):
                        logger.info(
                            "인덱스 소스 엑셀에 필수 컬럼 누락 → 리포지토리 샘플로 대체: %s",
                            canon_name,
                        )
                        return _table_from_parsed(
                            _parse_file_schema_for_table(demo_path, canon_name)
                        )
                    return _table_from_parsed(parsed_src)
                except Exception as exc:
                    logger.warning(
                        "테이블 소스 엑셀 재파싱 실패(메타 컬럼으로 대체 시도): %s — %s",
                        source_raw,
                        exc,
                    )

        cols = _columns_from_metadata(meta)

        have = {c.name for c in cols} if cols else set()
        meta_stale = (
            demo_path is not None
            and required is not None
            and not required.issubset(have)
        )
        if meta_stale:
            try:
                logger.info(
                    "Chroma 메타에 필수 컬럼 누락 → 리포지토리 샘플 엑셀로 스키마 보강: %s",
                    canon_name,
                )
                return _table_from_parsed(
                    _parse_file_schema_for_table(demo_path, canon_name)
                )
            except Exception as exc:
                logger.warning(
                    "샘플 엑셀 자가 치유 실패(메타 그대로 사용): %s — %s",
                    demo_path,
                    exc,
                )

        if cols:
            return TableSchema(
                table_name=canon_name,
                korean_name=str(meta.get("korean_name", "")),
                domain=str(meta.get("domain", "")),
                description=desc,
                source_file=source_raw,
                columns=cols,
            )

        if demo_path is not None:
            try:
                return _table_from_parsed(
                    _parse_file_schema_for_table(demo_path, canon_name)
                )
            except Exception as exc:
                logger.warning(
                    "데모 샘플 엑셀 재파싱 실패: %s — %s",
                    demo_path,
                    exc,
                )

        return TableSchema(
            table_name=canon_name,
            korean_name=str(meta.get("korean_name", "")),
            domain=str(meta.get("domain", "")),
            description=desc,
            source_file=source_raw,
            columns=cols,
        )

    def list_tables(
        self,
        domain: str | None = None,
        *,
        schema_pool: SchemaPool = "customer",
    ) -> list[dict[str, Any]]:
        """인덱싱된 테이블 목록을 반환합니다.

        Chroma는 메타데이터가 크거나 내부 이슈로 `metadatas[i]`가 None인 경우가 있어,
        항상 `ids`와 짝을 맞추고 메타가 없으면 id(테이블명)만으로 최소 행을 만듭니다.
        `collection.count()`와 목록 길이가 어긋나지 않게 합니다.
        """
        coll = self._get_collection(schema_pool)
        kwargs: dict[str, Any] = {"include": ["metadatas"]}
        if domain is not None:
            kwargs["where"] = {"domain": {"$eq": domain}}

        # 일부 Chroma 버전은 limit 미지정 시 일부 행만 반환할 수 있음
        try:
            n_docs = coll.count()
            if n_docs == 0:
                return []
            kwargs["limit"] = max(n_docs, 1)
        except Exception:
            pass

        res = coll.get(**kwargs)
        ids: list[str] = list(res.get("ids") or [])
        metas_raw = res.get("metadatas")
        metas: list[Any]
        if metas_raw is None:
            metas = [None] * len(ids)
        else:
            metas = list(metas_raw)
            if len(metas) < len(ids):
                metas.extend([None] * (len(ids) - len(metas)))

        by_canon: dict[str, tuple[dict[str, Any], str]] = {}
        for i, tid in enumerate(ids):
            raw = metas[i] if i < len(metas) else None
            if raw is None or not isinstance(raw, dict):
                d = {"table_name": str(tid)}
            else:
                d = dict(raw)
            d.pop("columns_json", None)
            if not (d.get("table_name") or "").strip():
                d["table_name"] = str(tid)
            canon = canonical_pool_table_name(
                str(d.get("table_name", tid))
            )
            d["table_name"] = canon
            tid_s = str(tid)
            prev = by_canon.get(canon)
            if prev is None:
                by_canon[canon] = (d, tid_s)
            else:
                _old_d, old_tid = prev
                new_id_matches = tid_s.upper() == canon
                old_id_matches = old_tid.upper() == canon
                if new_id_matches and not old_id_matches:
                    by_canon[canon] = (d, tid_s)

        rows = [pair[0] for pair in by_canon.values()]
        rows.sort(key=lambda r: str(r.get("table_name", "")))
        return rows

    def get_stats(self, *, schema_pool: SchemaPool = "customer") -> dict[str, Any]:
        """지정 풀의 벡터스토어 통계를 반환합니다."""
        coll = self._get_collection(schema_pool)
        res = coll.get(include=["metadatas"])
        ids = list(res.get("ids") or [])
        metas_raw = res.get("metadatas")
        if metas_raw is None:
            metas: list[Any] = [None] * len(ids)
        else:
            metas = list(metas_raw)
            if len(metas) < len(ids):
                metas.extend([None] * (len(ids) - len(metas)))

        by_domain: dict[str, int] = {}
        for i, _tid in enumerate(ids):
            m = metas[i] if i < len(metas) else None
            if not m or not isinstance(m, dict):
                dkey = ""
            else:
                dkey = str(m.get("domain", "") or "")
            by_domain[dkey] = by_domain.get(dkey, 0) + 1

        return {
            "total": coll.count(),
            "by_domain": by_domain,
            "collection": self._collection_name(schema_pool),
            "schema_pool": schema_pool,
            "model": self._settings.EMBEDDING_MODEL,
        }

    def get_stats_all(self) -> dict[str, Any]:
        """고객·관리자 풀 통계를 한 번에 반환합니다(관리자 UI용)."""
        return {
            "customer": self.get_stats(schema_pool="customer"),
            "admin": self.get_stats(schema_pool="admin"),
        }

    def delete_table(self, table_name: str, *, schema_pool: SchemaPool = "customer") -> bool:
        """단일 테이블을 벡터스토어에서 삭제합니다. 삭제 성공 시 True, 존재하지 않으면 False."""
        from backend.schema_naming import canonical_pool_table_name

        coll = self._get_collection(schema_pool)
        canonical = canonical_pool_table_name(table_name.upper())
        try:
            result = coll.get(ids=[canonical])
            if not result or not result.get("ids"):
                return False
            coll.delete(ids=[canonical])
            logger.info("테이블 삭제 완료: %s (%s)", canonical, schema_pool)
            return True
        except Exception:
            logger.exception("테이블 삭제 중 오류: %s (%s)", table_name, schema_pool)
            raise

    def reset(self, *, schema_pool: SchemaPool = "customer") -> None:
        """지정 풀의 컬렉션을 초기화합니다."""
        self._recreate_collection(schema_pool)
        logger.info(
            "컬렉션 초기화 완료: %s (%s)",
            self._collection_name(schema_pool),
            schema_pool,
        )

    # ------------------------------------------------------------------
    # 화면-테이블 매핑 (screen_table_map)
    # ------------------------------------------------------------------

    _SCREEN_MAP_COLLECTION = "screen_table_map"

    def _get_screen_map_collection(self) -> Collection:
        name = self._SCREEN_MAP_COLLECTION
        if name not in self._collection_cache:
            self._collection_cache[name] = self._chroma.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection_cache[name]

    def index_screen_map(self, screen_maps: list[dict[str, Any]]) -> dict[str, Any]:
        """화면-테이블 매핑 목록을 ChromaDB screen_table_map 컬렉션에 인덱싱합니다."""
        coll = self._get_screen_map_collection()
        indexed = 0
        errors: list[str] = []

        for sm in screen_maps:
            screen_id   = str(sm.get("screen_id", "")).strip()
            screen_name = str(sm.get("screen_name", "")).strip()
            tables: list[str] = [t for t in sm.get("tables", []) if t]
            service   = str(sm.get("service", "")).strip()
            dbio_file = str(sm.get("dbio_file", "")).strip()

            if not screen_id:
                errors.append("screen_id가 없어 건너뜁니다.")
                continue

            tables_str = ", ".join(tables) if tables else "(없음)"
            doc = (
                f"화면 {screen_id} ({screen_name})은 "
                f"서비스 {service}를 통해 DBIO {dbio_file}를 호출하며, "
                f"다음 테이블을 사용합니다: {tables_str}"
            )
            meta: dict[str, Any] = {
                "screen_id":   screen_id,
                "screen_name": screen_name,
                "tables":      ",".join(tables),
                "service":     service,
                "dbio_file":   dbio_file,
            }

            try:
                embedding = self._embed_one_with_retry(doc)
                coll.upsert(
                    ids=[screen_id],
                    documents=[doc],
                    embeddings=[embedding],
                    metadatas=[meta],
                )
                indexed += 1
                logger.info("screen_map 인덱싱 완료: %s (테이블 %s개)", screen_id, len(tables))
            except Exception as exc:
                msg = f"{screen_id}: {exc}"
                logger.exception("screen_map upsert 실패: %s", msg)
                errors.append(msg)

        return {"indexed": indexed, "errors": errors}

    def search_screen_map(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        """자연어로 화면-테이블 매핑을 검색합니다."""
        try:
            coll = self._get_screen_map_collection()
            n_docs = coll.count()
            if n_docs == 0:
                return []

            q_emb = self._embed_one_with_retry(query)
            raw = coll.query(
                query_embeddings=[q_emb],
                n_results=min(top_k, n_docs),
                include=["documents", "metadatas", "distances"],
            )

            out: list[dict[str, Any]] = []
            ids_list  = raw.get("ids") or []
            docs_list = raw.get("documents") or []
            meta_list = raw.get("metadatas") or []
            dist_list = raw.get("distances") or []

            if not ids_list or not ids_list[0]:
                return out

            for i, _id in enumerate(ids_list[0]):
                doc  = docs_list[0][i] if docs_list and docs_list[0] else ""
                meta = meta_list[0][i] if meta_list and meta_list[0] else {}
                dist = dist_list[0][i] if dist_list and dist_list[0] else 0.0
                score = float(1.0 - float(dist))
                tables_raw = (meta or {}).get("tables", "")
                tables = [t for t in tables_raw.split(",") if t] if tables_raw else []
                out.append({
                    "screen_id":   str((meta or {}).get("screen_id",   _id)),
                    "screen_name": str((meta or {}).get("screen_name", "")),
                    "tables":      tables,
                    "service":     str((meta or {}).get("service",     "")),
                    "dbio_file":   str((meta or {}).get("dbio_file",   "")),
                    "document":    doc,
                    "score":       score,
                })
            return out
        except Exception as exc:
            logger.warning("screen_map 검색 실패: %s", exc)
            return []

    def get_screen_map_stats(self) -> dict[str, Any]:
        """screen_table_map 컬렉션의 통계를 반환합니다."""
        try:
            coll = self._get_screen_map_collection()
            return {"total": coll.count(), "collection": self._SCREEN_MAP_COLLECTION}
        except Exception as exc:
            logger.warning("screen_map 통계 조회 실패: %s", exc)
            return {"total": 0, "collection": self._SCREEN_MAP_COLLECTION}
