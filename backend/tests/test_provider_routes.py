from app.main import app


def test_krx_and_dart_routes_exist_and_kis_is_disabled() -> None:
    paths = {route.path for route in app.routes}

    assert "/api/providers/status" in paths
    assert "/api/krx/stocks/{code}/daily" in paths
    assert "/api/krx/index/{market}/daily" in paths
    assert "/api/dart/company/{corp_code}" in paths
    assert "/api/dart/disclosures/{corp_code}" in paths
    assert not any(path.startswith("/api/kis") for path in paths)
