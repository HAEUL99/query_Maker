# Schema·Query (query-maker)

엑셀로 정의한 **테이블 스키마**를 벡터 DB에 넣고, **자연어 질의**로 **Oracle SQL** 또는 **SAS PROC SQL**을 생성하는 **Text-to-SQL RAG** 애플리케이션입니다.

---

## 이 프로젝트가 하는 일

1. **테이블 정의서(.xlsx)**를 읽어 스키마를 파싱합니다.
2. 스키마 텍스트를 **Gemini 임베딩**으로 벡터화해 **ChromaDB**에 저장합니다. **고객 풀**과 **관리자 풀**은 서로 다른 컬렉션으로 분리됩니다 (`CHROMA_COLLECTION_CUSTOMER` / `CHROMA_COLLECTION_ADMIN`).
3. 사용자 질문과 비슷한 테이블을 검색한 뒤, **Gemini**가 SQL 초안과 설명을 생성합니다.
4. **웹 UI**
   - **질의** 탭: **SAS PROC SQL**만 생성 (`schema_pool=customer`, 테이블명 `TBL_*`).
   - **관리자** 탭: 로그인 후 **Oracle SQL** 생성·정의서 업로드·풀별 인덱스 초기화 (`schema_pool=admin`, 테이블명 `TB_*`). Oracle은 **조회만** 또는 **DML 허용**(`oracle_profile`) 선택.

```text
[엑셀 정의서] → 파싱 → 임베딩·인덱싱(Chroma, 풀별 컬렉션)
[자연어 질의] → 유사 테이블 검색 → LLM → SAS(고객) 또는 Oracle(관리자) + 설명
```

---

## 깃허브에서 받은 뒤, 내 업무에 맞게 쓰기 (아주 쉬운 순서)

이 프로젝트는 **박스처럼** 잘 나뉘어 있습니다.  
**받기 → 비밀번호 넣기 → 우리 엑셀 넣기**만 하면 대부분의 팀에서 그대로 쓸 수 있습니다.  
아래는 **초등학생도 순서대로** 따라 할 수 있게 짧게 적었습니다.

### ① 프로젝트를 내 컴퓨터로 가져오기

둘 중 **편한 한 가지**만 하면 됩니다.

| 방법 | 할 일 |
|------|--------|
| **A. ZIP** | 깃허브 페이지에서 초록색 **Code** → **Download ZIP** → 압축 풀기 |
| **B. git** | 터미널에서 `git clone (저장소 주소)` |

압축을 풀었다면, 폴더 이름이 `query-maker`인지 확인합니다.  
이 폴더가 앞으로 **작업의 기준 주소**가 됩니다.

### ② 비밀 설정만 “우리 팀용”으로 바꾸기

1. `query-maker` 폴더로 들어갑니다.  
2. `.env.example` 파일을 **복사**해서 이름을 `.env`로 바꿉니다. (이미 있으면 건너뜀)  
3. `.env`를 메모장 등으로 열고, **`GOOGLE_API_KEY=`** 뒤에 **본인 API 키**만 붙여 넣습니다.  
4. 저장합니다.

> API 키는 **비밀번호**와 같습니다. 깃허브에 올리거나 카톡으로 보내지 마세요.

나머지 줄(`LLM_MODEL`, `EMBEDDING_MODEL` 등)은 **회사에서 쓰는 모델 이름**이 있으면 그때만 바꿔도 됩니다. 잘 모르겠으면 **그대로 두고** 먼저 돌려 봐도 됩니다.

### ③ 우리 회사 “테이블 정의서” 넣기

1. 회사에서 쓰는 **엑셀(.xlsx)**을 준비합니다.  
   - 파일 이름이 곧 **테이블 이름**이 됩니다. (규칙은 `backend/parser/excel_parser.py` 참고)  
2. 예: `data/excel/우리팀/` 같은 폴더를 만들고, 그 안에 엑셀을 넣습니다.  
3. 터미널에서 (반드시 `query-maker` 안에서):

   ```bash
   PYTHONPATH=. python scripts/index.py --dir data/excel/우리팀/ --pool customer --reset
   ```
   (관리자 전용 스키마면 `--pool admin`을 사용합니다.)

4. 끝에 **“총 N개”**처럼 숫자가 나오면 성공에 가깝습니다.

샘플만 써 보고 싶으면 README 아래쪽 **「빠른 시작」**의 샘플 명령을 그대로 따라 해도 됩니다.

### ④ (선택) 화면 글자·이름을 우리 팀 스타일로

- **브라우저 탭 제목·로고 옆 글자**  
  - `frontend/index.html`의 `<title>`  
  - `frontend/src/App.jsx` 안의 `Schema·Query` 같은 문구  
- 바꾼 뒤 저장하고, 프론트를 다시 켜면 반영됩니다.

### ⑤ (선택) SQL이 “우리 회사 말투”에 가깝게 나오게

- `backend/generator/prompts.py` 안에 **Oracle / SAS**용 안내 문장이 있습니다.  
- 여기 문장을 조금씩 고치면, 생성되는 SQL 설명 톤이 바뀔 수 있습니다.  
- **처음엔 안 건드려도** 됩니다.

### ⑥ (선택) 웹 주소가 다를 때 (회사 서버 등)

- 프론트가 백엔드를 부르는 주소는 **`frontend/src/api.js`** 맨 위의 `BASE`입니다.  
- 백엔드를 `8000`이 아닌 포트로 띄우면, 여기 숫자를 **같이** 맞춥니다.  
- 다른 PC에서 접속하게 하면, `backend/main.py`의 **CORS**에 그 PC의 주소를 추가해야 할 수 있습니다.

### ⑦ 동료에게 “이 폴더 줄 때” 체크

- **`.env`는 보내지 않기** (키가 들어 있음)  
- 대신 **`.env.example`만** 보내고, 키는 **각자 발급**하게 안내하기  
- 우리 팀만 쓰는 엑셀은 **회사 규정**에 맞게 별도 공유

---

## 폴더 구조 (요약)

```text
query-maker/
├── backend/                 # Python 백엔드
│   ├── main.py              # FastAPI 앱, CORS, lifespan, 예외 처리
│   ├── config.py            # .env 기반 설정
│   ├── models.py            # TableSchema, 검색/생성 결과 모델
│   ├── api/routes.py        # REST API (/api/query, /api/index, …)
│   ├── parser/excel_parser.py   # .xlsx → TableSchema
│   ├── vectorstore/chroma_store.py  # Chroma + Gemini 임베딩
│   └── generator/           # SQL 생성(Gemini), 프롬프트
├── frontend/                # React + Vite SPA
│   ├── src/
│   │   ├── App.jsx          # 메인 UI
│   │   ├── api.js           # 백엔드 fetch (BASE URL)
│   │   ├── ErrorBoundary.jsx
│   │   └── …
│   └── package.json
├── scripts/
│   ├── setup.py             # 초기 설치 자동화
│   ├── index.py             # CLI 인덱싱
│   ├── run.py               # 백엔드 + 프론트 동시 실행
│   ├── create_sample_data.py    # 샘플 .xlsx 생성
│   ├── bootstrap_demo_index.py # sample_* 폴더 정의서만으로 고객·관리자 풀 인덱싱
│   └── verify_e2e.py        # 파이프라인 검증 스크립트
├── data/excel/sample_customer/  # 고객 풀 샘플 TBL_*.xlsx
├── data/excel/sample_admin/     # 관리자 풀 샘플 TB_*.xlsx
├── chroma_db/               # Chroma 영속 저장(설정에 따라 경로 변경)
├── requirements.txt
├── .env                     # 로컬 비밀 설정(저장소에 올리지 말 것)
└── .env.example
```

---

## 사전 요구 사항

| 항목 | 권장 |
|------|------|
| Python | **3.11 이상** |
| Node.js | **18 이상** (프론트 개발 시) |
| Google AI | **Gemini API 키** ([Google AI Studio](https://aistudio.google.com/) 등) |

---

## 빠른 시작

### 1) 저장소에서 `query-maker`로 이동

모든 명령은 **`query-maker` 디렉터리**를 기준으로 실행하는 것이 안전합니다.  
(`.env`, `CHROMA_PERSIST_DIR=./chroma_db`, `PYTHONPATH`가 이 경로를 가정합니다.)

```bash
cd query-maker
```

### 2) 가상환경(선택) + Python 의존성

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3) 환경 변수

`.env.example`을 복사해 `.env`를 만들고 **`GOOGLE_API_KEY`**를 넣습니다.

```bash
cp .env.example .env
```

| 변수 | 설명 |
|------|------|
| `GOOGLE_API_KEY` | Gemini API 키 (**필수**) |
| `EMBEDDING_MODEL` | 임베딩 모델명 (예: `models/gemini-embedding-001`) |
| `LLM_MODEL` | SQL 생성용 LLM (예: `models/gemini-2.5-flash`) |
| `CHROMA_PERSIST_DIR` | Chroma 저장 경로 (기본 `./chroma_db`) |
| `CHROMA_COLLECTION_CUSTOMER` / `CHROMA_COLLECTION_ADMIN` | 고객·관리자 Chroma 컬렉션 이름 |
| `ADMIN_PASSWORD` | 관리자 로그인·Bearer 토큰 발급·업로드 API용 (**관리자 탭·`/api/index` 등에 필요**) |
| `ADMIN_JWT_SECRET` | (선택) JWT 서명용 별도 비밀. 비우면 `ADMIN_PASSWORD`로 서명 |
| `TABLE_NAME_POOL_VALIDATION` | `true`면 풀별 테이블명 규칙 검사 (고객 `TBL_*`, 관리자 `TB_*`) |
| `TOP_K_RESULTS` | 검색 시 가져올 테이블 후보 수 |
| `MAX_TOKENS_CONTEXT` | 프롬프트에 넣을 스키마 텍스트 상한(토큰 추정) |

### 4) 샘플 데이터·인덱싱

샘플 엑셀이 없으면:

```bash
PYTHONPATH=. python scripts/create_sample_data.py
```

`sample_customer/`·`sample_admin/`에 **이미 넣어 둔** `.xlsx`만으로 두 풀 인덱싱(샘플 엑셀을 새로 만들지 않음):

```bash
PYTHONPATH=. python scripts/bootstrap_demo_index.py
```

데모용 엑셀을 처음 만들 때만(수동): `PYTHONPATH=. python scripts/create_sample_data.py`

인덱싱(CLI) — **고객 풀**과 **관리자 풀**을 각각 넣습니다.

```bash
PYTHONPATH=. python scripts/index.py --dir data/excel/sample_customer/ --pool customer --reset
PYTHONPATH=. python scripts/index.py --dir data/excel/sample_admin/ --pool admin --reset
```

- `--pool`: `customer`(테이블명 `TBL_*`) / `admin`(`TB_*`).
- `--reset`: 해당 풀 컬렉션을 비운 뒤 다시 넣습니다.
- `--list`: 인덱싱된 테이블 목록만 출력합니다 (`--pool`과 함께).
- 자세한 옵션은 `python scripts/index.py --help` (또는 스크립트 상단 주석 참고).

### 5) 백엔드 + 프론트 한 번에 실행 (권장)

프로젝트 **루트**(`query-maker/`)에서:

```bash
npm install
cd frontend && npm install && cd ..
npm run dev
```

- API: **http://localhost:8000** · 문서: **http://localhost:8000/docs**  
- 브라우저 UI: **http://localhost:5173**  
- 한쪽 프로세스가 끝나면 나머지도 함께 종료됩니다(`Ctrl+C` 한 번).

### 6) 백엔드·프론트를 따로 실행할 때

**백엔드** (터미널 하나):

```bash
PYTHONPATH=. uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

**프론트** (다른 터미널):

```bash
cd frontend
npm install
npm run dev
```

- 프론트의 API 주소는 `frontend/src/api.js`의 `BASE`(**http://localhost:8000**)와 맞춰야 합니다.

---

## 한 번에 설치·실행하고 싶을 때

### 자동 설치 스크립트

```bash
python scripts/setup.py
```

Python/Node 버전 확인, 폴더 생성, `pip install`, `frontend`가 있으면 `npm install`, `.env` 복사, 샘플 `.xlsx` 없으면 생성 등을 순서대로 수행합니다.

### 백엔드 + 프론트 동시 실행

```bash
PYTHONPATH=. python scripts/run.py
```

`.env`에 유효한 `GOOGLE_API_KEY`가 있어야 하며, 백엔드(8000) 후 프론트(`npm run dev`)를 띄우고 브라우저를 엽니다. (Windows에서는 `npm.cmd` 사용.)

---

## 주요 API (요약)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/query` | 자연어 질의 → SQL 생성. 본문에 `dialect`(`sas` \| `oracle`), `schema_pool`(`customer` \| `admin`), `oracle_profile`(`select_only` \| `admin_dml`) 등. **SAS는 고객 풀만**, **Oracle은 관리자 풀만**이며 Oracle 요청 시 `Authorization: Bearer` 필요 |
| POST | `/api/auth/login` | `{ "password": "..." }` → 관리자 JWT (`ADMIN_PASSWORD` 설정 시) |
| POST | `/api/index` | `multipart/form-data`: `schema_pool`, `files[]` — **Bearer 필수** |
| POST | `/api/index/reset` | `?schema_pool=` — **Bearer 필수** |
| GET | `/api/tables` | `?domain=` · `?schema_pool=` (관리자 풀은 Bearer) |
| GET | `/api/tables/{table_name}` | 테이블 상세 (`schema_pool` 쿼리 등, Swagger 참고) |
| GET | `/api/stats` | 인덱스 통계 (`schema_pool`) |
| GET | `/api/schema/naming` | `TBL_*` / `TB_*` 명명 규칙·검증 설정 |
| GET | `/api/admin/stats/summary` | 고객·관리자 풀 통계 한 번에 — **Bearer** |

상세 스키마는 **Swagger UI** (`/docs`)에서 확인하세요.

---

## 웹 UI 사용 팁

- **질의** 탭 (로그인 불필요): 왼쪽 **고객 풀** 테이블 목록·카테고리 필터·컬럼 미리보기. 메인 영역은 **SAS PROC SQL**만 생성합니다. 입력창 아래 **고객 풀 즐겨찾기** 칩을 누르면 해당 자연어 질의로 곧바로 생성합니다(브라우저에 저장).
- **관리자** 탭: 비밀번호 로그인 후 **Oracle SQL** 영역(조회만 / DML 허용). **관리자 풀 즐겨찾기**는 질의 탭과 동일하게 풀별로 구분되어 표시됩니다. 정의서 **업로드**·풀별 **인덱스 초기화**·**관리자 풀** 테이블 미리보기는 로그인한 상태에서만 사용합니다.
- 인덱스에 테이블이 **0건**이면 API가 실패할 수 있습니다. 정의서를 `data/excel/sample_*` 등에 넣은 뒤 `bootstrap_demo_index.py` 또는 `index.py`로 인덱싱하세요.
- **초기화** 버튼: 해당 탭의 질의 입력만 비웁니다(결과 카드는 유지).

---

## CLI·검증 스크립트

| 스크립트 | 용도 |
|----------|------|
| `scripts/index.py` | 디렉터리/파일 단위 인덱싱, `--list` |
| `scripts/bootstrap_demo_index.py` | `sample_customer/`·`sample_admin/`에 **있는** `.xlsx`만 양 풀 인덱싱(샘플 자동 생성 안 함) |
| `scripts/create_sample_data.py` | (수동) 데모용 `.xlsx`를 두 폴더에 새로 만들 때만 사용 |
| `scripts/verify_e2e.py` | 파싱 → 인덱싱 → 검색 → SQL 생성까지 일괄 검증 |
| `scripts/run.py` | API + Vite 동시 기동 |

---

## 문제 해결

| 증상 | 확인 |
|------|------|
| 테이블이 0개로 보임 | `bootstrap_demo_index.py` 또는 `index.py --pool customer|admin`으로 인덱싱했는지, 백엔드와 같은 `CHROMA_PERSIST_DIR`인지 확인 후 `--reset` 재인덱싱. |
| 관리자 로그인·업로드 불가 | `.env`에 `ADMIN_PASSWORD`가 비어 있지 않은지 확인. 비어 있으면 `/api/auth/login`이 503입니다. |
| Oracle SQL 401/403 | 관리자 탭에서 로그인했는지, 세션 토큰이 만료되지 않았는지 확인. |
| SAS/Oracle 400 (풀 불일치) | 백엔드 규칙: SAS는 `schema_pool=customer`만, Oracle은 `schema_pool=admin`만. UI가 이에 맞게 호출합니다. |
| 즐겨찾기·생성이 동작하지 않음 | 인덱스가 비어 있으면 안내 후 중단될 수 있음. 정의서 넣은 뒤 `bootstrap_demo_index.py` 또는 `index.py`로 인덱싱. |
| 프론트에서 API 오류 | 백엔드가 8000에서 떠 있는지, `frontend/src/api.js`의 `BASE`와 CORS(`backend/main.py`) 확인. |
| SQL/임베딩 오류 | `.env`의 모델명이 키에서 허용되는지, 쿼터·네트워크 확인. |
| 화면이 하얗게 비음 | 브라우저 F12 콘솔·네트워크 탭의 `/api/*` 응답 확인. |

---

## 라이선스·보안

- **`.env`와 API 키는 Git에 커밋하지 마세요.**
- 내부/테스트용 구성이므로 배포 시 인증·HTTPS·역할 분리 등을 별도로 검토하세요.

---

## 개발 참고

- 백엔드: `PYTHONPATH=.` 또는 `query-maker`를 작업 디렉터리로 두고 모듈 `backend`를 import합니다.
- 프론트 빌드: `cd frontend && npm run build` → `frontend/dist/`.
- 엑셀 형식은 `backend/parser/excel_parser.py`를 따릅니다.
  - **레거시**: 파일명→테이블명, 2행부터 `##META##`·컬럼 정의(첫 시트).
  - **멀티 테이블(한 파일에 복수 테이블)**: 1행 헤더에 `테이블명` 또는 `TABLE_NAME` 열이 있으면 **파일명 대신 해당 열 값**이 테이블명이 됩니다. 같은 시트에 서로 다른 테이블명 행을 여러 개 둘 수 있습니다. 테이블별 한글명·도메인은 `##META##` 행으로 지정(파서 docstring 참고).
- SQL 생성 프롬프트: `backend/generator/prompts.py` (Oracle / SAS, `oracle_profile`별 분기).

질문이나 개선 아이디어는 이 저장소의 이슈/PR 정책에 맞춰 올려 주세요.
