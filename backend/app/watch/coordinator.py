from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from decimal import Decimal
from typing import Awaitable, Callable, Iterable

from app.holdings.catalog import HoldingsCatalog
from app.quotes.event_hub import QuoteEventHub, quote_event_hub
from app.quotes.models import QuoteCacheKey, QuoteSnapshot
from app.quotes.service import quote_service
from app.quotes.websocket_manager import quote_websocket_manager

from .policy import WatchPolicy, production_watch_policy


@dataclass(frozen=True, slots=True)
class WatchDemand:
    position_id: str
    plan_id: str
    plan_version: int
    market: str
    ticker: str
    stop_price: Decimal
    target1_price: Decimal | None
    target2_price: Decimal | None
    venue: str = "INTEGRATED"


@dataclass(frozen=True, slots=True)
class WatchReconcileResult:
    enabled: bool
    blocked_reason: str | None
    demand_count: int
    resource_count: int
    leased_count: int
    rejected_count: int


QuoteHandler = Callable[
    [WatchDemand, QuoteSnapshot],
    None | Awaitable[None],
]
CoverageHandler = Callable[
    [WatchDemand, str],
    None | Awaitable[None],
]


def load_active_plan_watch_demands(
    catalog: HoldingsCatalog,
) -> list[WatchDemand]:
    """
    Read the current OPEN Position + ACTIVE Plan set.

    This is a read-only projection. It does not create Watch settings, mutate a
    management plan, or make a quote/network request.
    """

    with catalog.connection() as conn:
        rows = conn.execute(
            """
            SELECT
                p.id AS position_id,
                s.market AS market,
                s.ticker AS ticker,
                mp.id AS plan_id,
                mp.plan_version AS plan_version,
                mp.stop_price AS stop_price,
                mp.target1_price AS target1_price,
                mp.target2_price AS target2_price
            FROM holding_position p
            JOIN monitored_stock s
              ON s.id=p.monitored_stock_id
            JOIN holding_management_plan mp
              ON mp.position_id=p.id
             AND mp.status='ACTIVE'
            WHERE p.status='OPEN'
              AND s.archived_at IS NULL
            ORDER BY s.market,s.ticker,p.id
            """
        ).fetchall()

    return [
        WatchDemand(
            position_id=str(row["position_id"]),
            plan_id=str(row["plan_id"]),
            plan_version=int(row["plan_version"]),
            market=str(row["market"]),
            ticker=str(row["ticker"]),
            stop_price=Decimal(str(row["stop_price"])),
            target1_price=(
                Decimal(str(row["target1_price"]))
                if row["target1_price"] is not None
                else None
            ),
            target2_price=(
                Decimal(str(row["target2_price"]))
                if row["target2_price"] is not None
                else None
            ),
        )
        for row in rows
    ]


class WatchCoordinator:
    """
    Keep server-side quote demand alive for current management plans.

    Browser EventSource demand and Watch demand share the existing
    QuoteWebSocketManager lease table, so the same market resource is naturally
    de-duplicated. Watch has its own QuoteEventHub subscription and therefore
    does not depend on a browser SSE connection being open.
    """

    def __init__(
        self,
        catalog: HoldingsCatalog,
        *,
        policy_provider: Callable[[], WatchPolicy] = production_watch_policy,
        demand_loader: Callable[[HoldingsCatalog], Iterable[WatchDemand]]
        = load_active_plan_watch_demands,
        resolve_key: Callable[..., QuoteCacheKey] = quote_service.resolve_key,
        websocket_manager=quote_websocket_manager,
        event_hub: QuoteEventHub = quote_event_hub,
        on_quote: QuoteHandler | None = None,
        on_coverage_issue: CoverageHandler | None = None,
        reconcile_interval_seconds: float = 10.0,
    ) -> None:
        self.catalog = catalog
        self.policy_provider = policy_provider
        self.demand_loader = demand_loader
        self.resolve_key = resolve_key
        self.websocket_manager = websocket_manager
        self.event_hub = event_hub
        self.on_quote = on_quote
        self.on_coverage_issue = on_coverage_issue
        self.reconcile_interval_seconds = max(
            1.0,
            float(reconcile_interval_seconds),
        )
        self._demands_by_key: dict[QuoteCacheKey, tuple[WatchDemand, ...]] = {}
        self._consumer_tasks: dict[QuoteCacheKey, asyncio.Task[None]] = {}
        self._run_task: asyncio.Task[None] | None = None
        self._stop_requested = False

    @staticmethod
    async def _maybe_await(value) -> None:
        if inspect.isawaitable(value):
            await value

    async def _emit_coverage_issue(
        self,
        demands: tuple[WatchDemand, ...],
        reason: str,
    ) -> None:
        if self.on_coverage_issue is None:
            return
        for demand in demands:
            await self._maybe_await(
                self.on_coverage_issue(demand, reason)
            )

    async def _consume(self, key: QuoteCacheKey) -> None:
        queue = await self.event_hub.subscribe(key)
        try:
            while True:
                snapshot = await queue.get()
                handler = self.on_quote
                if handler is None:
                    continue
                for demand in self._demands_by_key.get(key, ()):
                    await self._maybe_await(handler(demand, snapshot))
        except asyncio.CancelledError:
            raise
        finally:
            await self.event_hub.unsubscribe(key, queue)

    async def _remove_key(self, key: QuoteCacheKey) -> None:
        self._demands_by_key.pop(key, None)
        task = self._consumer_tasks.pop(key, None)
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _clear_consumers(self) -> None:
        for key in tuple(self._consumer_tasks):
            await self._remove_key(key)
        self._demands_by_key.clear()

    async def reconcile_once(self) -> WatchReconcileResult:
        policy = self.policy_provider()
        if not policy.enabled:
            await self._clear_consumers()
            return WatchReconcileResult(
                enabled=False,
                blocked_reason=policy.blocked_reason,
                demand_count=0,
                resource_count=0,
                leased_count=0,
                rejected_count=0,
            )

        policy.require_enabled()
        demands = tuple(self.demand_loader(self.catalog))
        grouped: dict[QuoteCacheKey, list[WatchDemand]] = {}

        for demand in demands:
            key = self.resolve_key(
                market=demand.market,
                ticker=demand.ticker,
                venue=demand.venue,
            )
            grouped.setdefault(key, []).append(demand)

        desired = set(grouped)
        known = set(self._demands_by_key) | set(self._consumer_tasks)
        for key in tuple(known):
            if key not in desired:
                await self._remove_key(key)

        leased = 0
        rejected = 0
        for key, items in grouped.items():
            item_tuple = tuple(items)
            self._demands_by_key[key] = item_tuple
            accepted = bool(self.websocket_manager.touch_demand(key))
            if not accepted:
                rejected += 1
                await self._emit_coverage_issue(
                    item_tuple,
                    self.websocket_manager.subscription_error(key)
                    or "SUBSCRIPTION_REJECTED",
                )
                task = self._consumer_tasks.pop(key, None)
                if task is not None:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                continue

            leased += 1
            task = self._consumer_tasks.get(key)
            if task is None or task.done():
                self._consumer_tasks[key] = asyncio.create_task(
                    self._consume(key),
                    name=f"watch-quote-{key.market}-{key.ticker}-{key.venue}",
                )

        return WatchReconcileResult(
            enabled=True,
            blocked_reason=None,
            demand_count=len(demands),
            resource_count=len(grouped),
            leased_count=leased,
            rejected_count=rejected,
        )

    async def run(self) -> None:
        self._stop_requested = False
        while not self._stop_requested:
            try:
                await self.reconcile_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Coverage persistence/logging is added in P4-S1-C. A coordinator
                # loop must not crash the API process because one reconcile fails.
                pass
            await asyncio.sleep(self.reconcile_interval_seconds)

    async def start(self) -> None:
        if self._run_task is None or self._run_task.done():
            self._stop_requested = False
            self._run_task = asyncio.create_task(
                self.run(),
                name="holding-watch-coordinator",
            )

    async def stop(self) -> None:
        self._stop_requested = True
        task = self._run_task
        self._run_task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await self._clear_consumers()
