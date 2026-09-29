from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_holdings_watch_exposes_runtime_health_and_notification_inbox():
    panel = (
        ROOT / "src/components/HoldingWatchStatus.tsx"
    ).read_text(encoding="utf-8")
    client = (
        ROOT / "src/services/watchApi.ts"
    ).read_text(encoding="utf-8")

    assert "getWatchStatus" in panel
    assert "getWatchNotifications" in panel
    assert "markWatchNotificationRead" in panel
    assert "Watch 정책" in panel
    assert "시세 연결" in panel
    assert "실행 연속성" in panel
    assert "미확인 알림" in panel
    assert "알림 보기" in panel
    assert "감시 연속성 미확인" in panel

    assert '"/api/watch/status"' in client
    assert '"/api/watch/notifications?' in client
    assert "/read" in client


def test_watch_notifications_are_not_auto_read_on_load():
    panel = (
        ROOT / "src/components/HoldingWatchStatus.tsx"
    ).read_text(encoding="utf-8")

    load_start = panel.index("async function loadWatchOverview")
    confirm_start = panel.index("async function confirmNotification")
    load_block = panel[load_start:confirm_start]

    assert "markWatchNotificationRead" not in load_block
    assert "markWatchNotificationRead(notificationId)" in panel
    assert '>{"확인"}<' not in panel
    assert '"확인"' in panel


def test_watch_observability_ui_does_not_claim_production_policy_is_active():
    panel = (
        ROOT / "src/components/HoldingWatchStatus.tsx"
    ).read_text(encoding="utf-8")

    assert '"정책 검증 중"' in panel
    assert 'systemStatus?.policy_enabled' in panel
    assert "OPERATING_THRESHOLDS_UNAPPROVED" not in panel
    assert "자동 주문" not in panel
