from __future__ import annotations

import re
import sys
from pathlib import Path


def sanitize(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip()).strip("-_").lower()
    return cleaned[:32]


def main() -> int:
    if len(sys.argv) != 2:
        print("사용법: python backend/tools/set_repro_machine.py home")
        print("예시: home 또는 school")
        return 2
    label = sanitize(sys.argv[1])
    if not label:
        print("유효한 machine label이 필요합니다.")
        return 2

    backend_root = Path(__file__).resolve().parents[1]
    target = backend_root / "runtime" / "reproducibility" / "machine_label.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(label + "\n", encoding="utf-8")
    print(f"StockScope 재현성 비교 PC 라벨: {label}")
    print(f"저장 위치: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
