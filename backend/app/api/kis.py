from datetime import date, timedelta

from fastapi import APIRouter, Header, HTTPException, Query, status

from app.market.kis.client import KisApiError, KisReadOnlyClient
from app.market.kis.models import (
    DailyChartResponse,
    KisCredentials,
    KisSessionResponse,
    KisSessionStatus,
    StockQuote,
)
from app.market.kis.session import KisSession, kis_sessions


router = APIRouter(prefix="/kis", tags=["kis-read-only"])
client = KisReadOnlyClient()


def _session_or_401(session_id: str | None) -> KisSession:
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="KIS session is required.")
    session = kis_sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="KIS session expired or not found.")
    return session


def _bad_gateway(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router.post("/session", response_model=KisSessionResponse)
async def connect_kis(credentials: KisCredentials) -> KisSessionResponse:
    """Validate user-owned KIS credentials and create an ephemeral read-only session."""
    try:
        access_token, expires_in = await client.issue_access_token(credentials)
    except KisApiError as exc:
        raise _bad_gateway(exc) from exc
    session_id, session = kis_sessions.create(
        app_key=credentials.app_key,
        app_secret=credentials.app_secret,
        access_token=access_token,
        environment=credentials.environment,
        expires_in=expires_in,
    )
    return KisSessionResponse(
        session_id=session_id,
        environment=credentials.environment,
        expires_in=session.seconds_remaining,
    )


@router.get("/session", response_model=KisSessionStatus)
async def kis_session_status(x_kis_session: str | None = Header(default=None)) -> KisSessionStatus:
    session = kis_sessions.get(x_kis_session) if x_kis_session else None
    if session is None:
        return KisSessionStatus(connected=False)
    return KisSessionStatus(
        connected=True,
        environment=session.environment,
        expires_in=session.seconds_remaining,
    )


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_kis(x_kis_session: str | None = Header(default=None)) -> None:
    if x_kis_session:
        kis_sessions.delete(x_kis_session)


@router.get("/stocks/{symbol}/quote", response_model=StockQuote)
async def stock_quote(symbol: str, x_kis_session: str | None = Header(default=None)) -> StockQuote:
    session = _session_or_401(x_kis_session)
    try:
        return await client.get_quote(
            app_key=session.app_key,
            app_secret=session.app_secret,
            access_token=session.access_token,
            environment=session.environment,
            symbol=symbol,
        )
    except KisApiError as exc:
        raise _bad_gateway(exc) from exc


@router.get("/stocks/{symbol}/daily", response_model=DailyChartResponse)
async def stock_daily_chart(
    symbol: str,
    x_kis_session: str | None = Header(default=None),
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=60)),
    end_date: date = Query(default_factory=date.today),
    period: str = Query(default="D", pattern="^[DWMY]$"),
    adjusted: bool = Query(default=True),
) -> DailyChartResponse:
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="end_date must be on or after start_date.")
    if (end_date - start_date).days > 3660:
        raise HTTPException(status_code=422, detail="PoC query range is limited to 10 years.")
    session = _session_or_401(x_kis_session)
    try:
        return await client.get_daily_chart(
            app_key=session.app_key,
            app_secret=session.app_secret,
            access_token=session.access_token,
            environment=session.environment,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            period=period,
            adjusted=adjusted,
        )
    except KisApiError as exc:
        raise _bad_gateway(exc) from exc
