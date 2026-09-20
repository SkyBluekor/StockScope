from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

BASELINE_SHA256 = {
    "backend/app/backtest/candidate_priority.py": "5e5f19b45b660613bd4e06f3b9609c5ddff972be0db1e653f9a5b2a59f55e08f",
    "backend/app/backtest/reproducibility_audit.py": "b72aad97386d34249f078c713b7773ef012a956cff25d66409f302707b5c828b",
    "backend/app/backtest/scanner_quality/decision_quality_audit.py": "6cd13c21a45fb3c1663c1af5ab714e878ac07dca167105017a7eb1a42fbcc766",
}

OLD_VERSION = 'VERSION = "0.21.3.6"'
NEW_VERSION = 'VERSION = "0.21.3.7"'
HISTORICAL_GUARD = 'HISTORICAL_EVIDENCE_POLICY_VERSION = "v2"'


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    payload_root = project_root / "b25c_payload"
    if not payload_root.exists():
        raise SystemExit(f"B.2.5-C payload not found: {payload_root}")

    plan: list[tuple[Path, Path]] = []
    errors: list[str] = []

    for relative, expected_hash in BASELINE_SHA256.items():
        target = project_root / relative
        payload = payload_root / relative
        if not target.exists():
            errors.append(f"missing target: {relative}")
            continue
        if not payload.exists():
            errors.append(f"missing payload: {relative}")
            continue
        current_hash = _sha256(target)
        payload_hash = _sha256(payload)
        if current_hash == payload_hash:
            continue
        if current_hash != expected_hash:
            errors.append(
                f"working tree changed: {relative}\n"
                f"  expected pre-C sha256: {expected_hash}\n"
                f"  actual sha256:         {current_hash}"
            )
            continue
        plan.append((payload, target))

    scanner = project_root / "backend/app/backtest/scanner.py"
    if not scanner.exists():
        errors.append("missing target: backend/app/backtest/scanner.py")
        scanner_text = ""
    else:
        scanner_text = scanner.read_text(encoding="utf-8")
        if NEW_VERSION not in scanner_text:
            if OLD_VERSION not in scanner_text:
                errors.append("scanner.py is not decision version 0.21.3.6; refusing to overwrite it")
            if HISTORICAL_GUARD not in scanner_text:
                errors.append("scanner.py does not contain Historical Evidence policy v2 guard")

    test_src = payload_root / "backend/tests/test_candidate_priority_v0214b25c.py"
    test_dst = project_root / "backend/tests/test_candidate_priority_v0214b25c.py"
    if not test_src.exists():
        errors.append("missing payload test: backend/tests/test_candidate_priority_v0214b25c.py")

    if errors:
        joined = "\n\n".join(errors)
        raise SystemExit(
            "B.2.5-C preflight failed. No production files were changed.\n\n" + joined
        )

    for payload, target in plan:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(payload, target)
        print(f"updated: {target.relative_to(project_root)}")

    if NEW_VERSION not in scanner_text:
        scanner.write_text(scanner_text.replace(OLD_VERSION, NEW_VERSION, 1), encoding="utf-8")
        print("updated: backend/app/backtest/scanner.py VERSION 0.21.3.6 -> 0.21.3.7")
    else:
        print("scanner decision version already 0.21.3.7")

    if _sha256(test_dst) != _sha256(test_src) if test_dst.exists() else True:
        shutil.copy2(test_src, test_dst)
        print("updated: backend/tests/test_candidate_priority_v0214b25c.py")

    print("B.2.5-C apply complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
