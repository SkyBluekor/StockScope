from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_main_scanner_subscribes_to_results_completed_by_embedded_runner():
    text = (ROOT / "src/components/ScannerPanel.tsx").read_text(encoding="utf-8")
    assert "useScannerSession" in text
    assert "TRACK.1.10.1: accept Scanner results completed from another entry point" in text
    assert "const sharedSession = useScannerSession();" in text
    assert "setResult(sharedSession.result)" in text
