from app.core.trading_policy import FORBIDDEN_ORDER_TERMS
from app.main import app


def test_no_real_order_routes_exist() -> None:
    route_paths = [route.path.lower() for route in app.routes]
    violations: list[tuple[str, str]] = []

    for path in route_paths:
        for term in FORBIDDEN_ORDER_TERMS:
            if term.isascii() and term in path:
                violations.append((path, term))

    assert not violations, f"Forbidden brokerage routes detected: {violations}"
