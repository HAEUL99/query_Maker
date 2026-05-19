#!/usr/bin/env python3
"""`data/excel/sample_customer/`·`sample_admin/`에 이미 있는 정의서만 인덱싱합니다.

샘플 엑셀을 새로 만들지 않습니다. 처음 데모용 파일이 필요하면 수동으로:
  PYTHONPATH=. python scripts/create_sample_data.py

  cd query-maker
  PYTHONPATH=. python scripts/bootstrap_demo_index.py

전제: `.env`에 GOOGLE_API_KEY (임베딩 API 호출)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list[str]) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_ROOT)
    r = subprocess.run(cmd, cwd=_ROOT, env=env)
    if r.returncode != 0:
        sys.exit(r.returncode)


def main() -> None:
    def idx(pool: str, dir_name: str) -> None:
        d = _ROOT / "data" / "excel" / dir_name
        if not d.is_dir():
            print(f"[경고] 폴더 없음(건너뜀): {d}", file=sys.stderr)
            return
        xlsx = sorted(d.glob("*.xlsx"))
        xlsx = [p for p in xlsx if not p.name.startswith("~$")]
        if not xlsx:
            print(f"[경고] .xlsx 없음(건너뜀): {d}", file=sys.stderr)
            return
        print(f"→ 인덱싱 풀={pool}  dir={d}  ({len(xlsx)}개 파일) …")
        _run(
            [
                sys.executable,
                str(_ROOT / "scripts" / "index.py"),
                "--dir",
                str(d),
                "--pool",
                pool,
                "--reset",
            ],
        )

    idx("customer", "sample_customer")
    idx("admin", "sample_admin")

    print("\n✓ 완료: 위 폴더에 있던 정의서 기준으로 고객·관리자 풀 인덱싱(시도)됨.")


if __name__ == "__main__":
    main()
