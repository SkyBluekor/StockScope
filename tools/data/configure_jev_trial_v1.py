from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for candidate in (ROOT, BACKEND):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.jev import JevCatalog, JevCatalogError
from app.jev.trial import JevTrialError, configure_trial_protocol
from tools.data.common import simulation_db_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Frozen JEV Reviewer Trial V1을 runtime DB에 configure합니다. "
            "이 작업은 network를 활성화하거나 모델을 호출하지 않습니다."
        )
    )
    parser.add_argument("--simulation-db", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    path = Path(args.simulation_db or simulation_db_path())
    try:
        result = configure_trial_protocol(JevCatalog(path))
        print("JEV TRIAL V1 CONFIGURE PASS")
        print(result)
        return 0
    except (JevCatalogError, JevTrialError) as exc:
        print(
            f"ERROR [{getattr(exc, 'code', 'JEV_TRIAL_ERROR')}]: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
