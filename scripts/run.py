"""백엔드(uvicorn)와 프론트엔드(npm run dev)를 동시에 띄웁니다."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_DEFAULT_KEY_MARKERS = frozenset(
    {
        "",
        "여기에_AI_Studio_키_입력",
        "your-api-key",
        "YOUR_API_KEY",
        "changeme",
    }
)


def _read_google_api_key() -> str | None:
    env_file = _ROOT / ".env"
    if not env_file.is_file():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("GOOGLE_API_KEY="):
            return s.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _chroma_dir_empty_or_missing() -> bool:
    from backend.config import get_settings

    p = Path(get_settings().CHROMA_PERSIST_DIR)
    if not p.is_absolute():
        p = _ROOT / p
    if not p.resolve().exists():
        return True
    try:
        children = list(p.iterdir())
    except OSError:
        return True
    return len(children) == 0


def main() -> None:
    os.chdir(_ROOT)

    env_path = _ROOT / ".env"
    if not env_path.is_file():
        print(f"[오류] .env 파일이 없습니다: {env_path}", file=sys.stderr)
        print("  scripts/setup.py 를 먼저 실행하거나 .env를 만드세요.", file=sys.stderr)
        sys.exit(1)

    key = _read_google_api_key()
    if key is None or key.strip() in _DEFAULT_KEY_MARKERS:
        print(
            "[오류] GOOGLE_API_KEY가 비어 있거나 기본 플레이스홀더입니다. "
            ".env에 유효한 키를 입력하세요.",
            file=sys.stderr,
        )
        sys.exit(1)

    if _chroma_dir_empty_or_missing():
        print(
            "[경고] chroma_db/가 비어 있거나 없습니다. "
            "검색·SQL 생성 전에 인덱싱이 필요할 수 있습니다.\n"
            "  예: python scripts/index.py --dir data/excel/sample_customer/ --pool customer",
            file=sys.stderr,
        )

    run_env = os.environ.copy()
    run_env["PYTHONPATH"] = str(_ROOT)

    backend_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ]
    backend_proc: subprocess.Popen | None = None
    frontend_proc: subprocess.Popen | None = None

    try:
        backend_proc = subprocess.Popen(
            backend_cmd,
            cwd=_ROOT,
            env=run_env,
        )
        time.sleep(2)

        fe = _ROOT / "frontend"
        if fe.is_dir():
            npm = "npm.cmd" if sys.platform == "win32" else "npm"
            frontend_proc = subprocess.Popen(
                [npm, "run", "dev"],
                cwd=fe,
                env=run_env,
            )

        time.sleep(3)
        webbrowser.open("http://localhost:5173")

        # 자식 프로세스가 살아 있는 동안 대기 (Ctrl+C 로 KeyboardInterrupt)
        while True:
            if backend_proc.poll() is not None:
                print("백엔드 프로세스가 종료되었습니다.", file=sys.stderr)
                break
            if frontend_proc is not None and frontend_proc.poll() is not None:
                print("프론트엔드 프로세스가 종료되었습니다.", file=sys.stderr)
                break
            time.sleep(0.4)
    except KeyboardInterrupt:
        print("\n종료 신호 수신 — 프로세스를 정리합니다 …", file=sys.stderr)
    finally:
        for p in (frontend_proc, backend_proc):
            if p is not None and p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait(timeout=3)


if __name__ == "__main__":
    main()
