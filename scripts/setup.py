"""query-maker 초기 설치를 자동화합니다."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _ensure_python() -> None:
    if sys.version_info < (3, 11):
        print(
            f"[오류] Python 3.11 이상이 필요합니다. 현재: {sys.version.split()[0]}",
            file=sys.stderr,
        )
        sys.exit(1)


def _ensure_node() -> None:
    try:
        out = subprocess.check_output(
            ["node", "-v"],
            stderr=subprocess.STDOUT,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"[오류] Node.js를 실행할 수 없습니다: {exc}", file=sys.stderr)
        sys.exit(1)

    # v18.2.0 또는 v20.10.0
    ver = out.lstrip("v")
    major_str = ver.split(".", 1)[0]
    try:
        major = int(major_str)
    except ValueError:
        print(f"[오류] Node.js 버전을 해석할 수 없습니다: {out!r}", file=sys.stderr)
        sys.exit(1)
    if major < 18:
        print(
            f"[오류] Node.js 18 이상이 필요합니다. 현재: {out}",
            file=sys.stderr,
        )
        sys.exit(1)


def _mkdirs() -> None:
    (_ROOT / "data" / "excel").mkdir(parents=True, exist_ok=True)
    (_ROOT / "data" / "excel" / "sample_customer").mkdir(
        parents=True, exist_ok=True
    )
    (_ROOT / "data" / "excel" / "sample_admin").mkdir(parents=True, exist_ok=True)
    (_ROOT / "chroma_db").mkdir(parents=True, exist_ok=True)


def _pip_install() -> None:
    req = _ROOT / "requirements.txt"
    if not req.is_file():
        print(f"[오류] requirements.txt 없음: {req}", file=sys.stderr)
        sys.exit(1)
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(req)],
        cwd=_ROOT,
    )
    if r.returncode != 0:
        sys.exit(1)


def _npm_install_if_frontend() -> None:
    fe = _ROOT / "frontend"
    if not fe.is_dir():
        return
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    r = subprocess.run([npm, "install"], cwd=fe)
    if r.returncode != 0:
        sys.exit(1)


def _copy_env_example() -> None:
    env_path = _ROOT / ".env"
    ex = _ROOT / ".env.example"
    if env_path.is_file():
        return
    if not ex.is_file():
        print(f"[경고] .env.example 없음 — .env 수동 생성 필요: {ex}", file=sys.stderr)
        return
    shutil.copy(ex, env_path)
    print(f".env 생성: {env_path} (.env.example 복사)")


def _hint_sample_xlsx() -> None:
    """데모용 엑셀은 자동 생성하지 않습니다. 필요 시 수동으로 create_sample_data.py 실행."""
    sample_c = _ROOT / "data" / "excel" / "sample_customer"
    sample_a = _ROOT / "data" / "excel" / "sample_admin"
    has_c = any(p for p in sample_c.glob("*.xlsx") if not p.name.startswith("~$"))
    has_a = any(p for p in sample_a.glob("*.xlsx") if not p.name.startswith("~$"))
    if has_c or has_a:
        return
    print(
        "안내: data/excel/sample_customer·sample_admin/에 .xlsx가 없습니다. "
        "데모용 생성은 수동으로: PYTHONPATH=. python scripts/create_sample_data.py",
        file=sys.stderr,
    )


def main() -> None:
    print("query-maker 설치를 시작합니다 …\n")
    _ensure_python()
    _ensure_node()
    _mkdirs()
    _pip_install()
    _npm_install_if_frontend()
    _copy_env_example()
    _hint_sample_xlsx()

    print(
        """
✅ 설치 완료!
   다음 단계:
   1. .env 파일에 GOOGLE_API_KEY 입력
   2. python scripts/index.py --dir data/excel/sample_customer/ --pool customer
      python scripts/index.py --dir data/excel/sample_admin/ --pool admin
   3. python scripts/run.py
"""
    )


if __name__ == "__main__":
    main()
