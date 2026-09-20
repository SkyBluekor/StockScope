from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.simulation.sim1_enums import PositionSource, PositionStatus, SimulationMode
from app.simulation.sim1_service import SimulationPortfolioService
from app.simulation.sim1_store import BaselineRegistry, SimulationRepository
from app.simulation.sim2_commands import BuyCommand
from app.simulation.sim2_trading_service import SimulationTradingService
from app.simulation.sim3_api import AdvanceRequest, CreateSessionRequest
from app.simulation.sim3_clock import PriceStatus
from app.simulation.sim3_market_provider import HistoricalMarketBar, HistoricalMarketStoreProvider
from app.simulation.sim3_playback_service import MarketPlaybackService, SimulationPlaybackError
from app.simulation.sim3_store import SimulationPlaybackStore

NOW = datetime(2026, 9, 20, 13, 0, tzinfo=timezone.utc)
BASELINE_ID = "SS-SCANNER-0.21.3.7-testbaseline"
D1 = date(2025, 1, 2)
D2 = date(2025, 1, 3)
D3 = date(2025, 1, 6)
D4 = date(2025, 1, 7)
D5 = date(2025, 1, 8)


def bar(code, day, close, market="KOSPI", volume=1000):
    c = Decimal(str(close))
    return HistoricalMarketBar(code, market, day, c-Decimal("100"), c+Decimal("200"), c-Decimal("300"), c, volume)


class FakeProvider:
    def __init__(self, days=(D1,D2,D3,D4,D5), bars=None):
        self.days = list(days)
        self.bars = bars or {}
        self.calls = []

    def has_trading_day(self, day): return day in self.days
    def next_trading_day(self, day):
        later=[d for d in self.days if d>day]
        return min(later) if later else None
    def previous_trading_day(self, day):
        earlier=[d for d in self.days if d<day]
        return max(earlier) if earlier else None
    def get_bar(self, market, stock_code, trading_date):
        self.calls.append((market, stock_code, trading_date))
        return self.bars.get((market,stock_code,trading_date)) or self.bars.get(("KRX",stock_code,trading_date))


@pytest.fixture()
def env(tmp_path: Path):
    baseline_dir=tmp_path/"backend/runtime/baseline"; baseline_dir.mkdir(parents=True)
    (baseline_dir/"scanner-production-baseline_0.21.3.7.json").write_text(json.dumps({"baseline_id":BASELINE_ID}),encoding="utf-8")
    repo=SimulationRepository(tmp_path/"backend/runtime/simulation/simulation.db")
    ps=SimulationPortfolioService(repo,BaselineRegistry(baseline_dir)); ps.initialize()
    bars={
      ("KOSPI","005930",D1):bar("005930",D1,"80000"),
      ("KOSPI","005930",D2):bar("005930",D2,"81500"),
      ("KOSPI","005930",D3):bar("005930",D3,"78900"),
      ("KOSPI","005930",D4):bar("005930",D4,"83000"),
      ("KOSPI","005930",D5):bar("005930",D5,"84000"),
      ("KOSDAQ","035720",D1):bar("035720",D1,"50000",market="KOSDAQ"),
      ("KOSDAQ","035720",D2):bar("035720",D2,"51000",market="KOSDAQ"),
      ("KOSDAQ","035720",D3):bar("035720",D3,"52000",market="KOSDAQ"),
    }
    provider=FakeProvider(bars=bars)
    playback=MarketPlaybackService(repo,ps,provider); playback.initialize()
    return tmp_path,repo,ps,provider,playback


def make_portfolio(ps, mode=SimulationMode.HISTORICAL):
    return ps.create_portfolio(name="Sim",initial_cash="10000000",mode=mode,now=NOW)


def make_position(ps,p, code="005930", market="KOSPI", qty=10, entry="80000", current="80000"):
    return ps.create_position_state(portfolio_id=p.id,stock_code=code,stock_name=code,market=market,source=PositionSource.MANUAL,quantity=qty,average_entry_price=entry,current_price=current,opened_at=NOW)


def active(playback,p,start=D1,end=D5):
    return playback.create_session(p.id,start_date=start,end_date=end,now=NOW)


def errcode(exc): return exc.value.code


def test_01_schema_is_v3(env): assert env[1].schema_version()==3

def test_02_session_create(env):
    _,_,ps,_,pb=env; p=make_portfolio(ps); s=active(pb,p); assert s.current_date==D1 and s.status.value=="ACTIVE"

def test_03_start_saved(env):
    _,repo,ps,_,pb=env; p=make_portfolio(ps); s=active(pb,p); assert SimulationPlaybackStore(repo).get_session(s.id).start_date==D1

def test_04_end_saved(env):
    _,repo,ps,_,pb=env; p=make_portfolio(ps); s=active(pb,p); assert SimulationPlaybackStore(repo).get_session(s.id).end_date==D5

def test_05_current_initialized(env):
    _,_,ps,_,pb=env; p=make_portfolio(ps); assert active(pb,p).current_date==D1

def test_06_invalid_start_rejected(env):
    _,_,ps,_,pb=env; p=make_portfolio(ps)
    with pytest.raises(SimulationPlaybackError) as e: pb.create_session(p.id,start_date=date(2025,1,4))
    assert errcode(e)=="SIM_INVALID_TRADING_DATE"

def test_07_invalid_end_rejected(env):
    _,_,ps,_,pb=env; p=make_portfolio(ps)
    with pytest.raises(SimulationPlaybackError) as e: pb.create_session(p.id,start_date=D1,end_date=date(2025,1,4))
    assert errcode(e)=="SIM_INVALID_TRADING_DATE"

def test_08_invalid_range_rejected(env):
    _,_,ps,_,pb=env; p=make_portfolio(ps)
    with pytest.raises(SimulationPlaybackError) as e: pb.create_session(p.id,start_date=D3,end_date=D2)
    assert errcode(e)=="SIM_INVALID_DATE_RANGE"

def test_09_one_active_only(env):
    _,_,ps,_,pb=env; p=make_portfolio(ps); active(pb,p)
    with pytest.raises(SimulationPlaybackError) as e: active(pb,p)
    assert errcode(e)=="SIM_SESSION_ALREADY_ACTIVE"

def test_10_manual_mode_rejected(env):
    _,_,ps,_,pb=env; p=make_portfolio(ps,SimulationMode.MANUAL_TRACKING)
    with pytest.raises(SimulationPlaybackError) as e: active(pb,p)
    assert errcode(e)=="SIM_INVALID_MODE_FOR_DATE_ENGINE"

def test_11_next_day(env):
    _,_,ps,_,pb=env; p=make_portfolio(ps); active(pb,p); assert pb.next_day(p.id,now=NOW).current_date==D2

def test_12_weekend_skipped(env):
    _,_,ps,_,pb=env; p=make_portfolio(ps); active(pb,p,start=D2,end=D5); assert pb.next_day(p.id,now=NOW).current_date==D3

def test_13_previous_without_trade(env):
    _,_,ps,_,pb=env; p=make_portfolio(ps); active(pb,p); pb.next_day(p.id,now=NOW); assert pb.previous_day(p.id,now=NOW).current_date==D1

def test_14_start_range_blocks_previous(env):
    _,_,ps,_,pb=env; p=make_portfolio(ps); active(pb,p)
    with pytest.raises(SimulationPlaybackError) as e: pb.previous_day(p.id)
    assert errcode(e)=="SIM_START_OF_RANGE"

def test_15_end_range_blocks(env):
    _,_,ps,_,pb=env; p=make_portfolio(ps); active(pb,p,start=D1,end=D2); pb.next_day(p.id)
    with pytest.raises(SimulationPlaybackError) as e: pb.next_day(p.id)
    assert errcode(e)=="SIM_END_OF_RANGE"

def test_16_end_of_market_data(env):
    _,_,ps,provider,pb=env; p=make_portfolio(ps); active(pb,p,start=D5,end=None)
    with pytest.raises(SimulationPlaybackError) as e: pb.next_day(p.id)
    assert errcode(e)=="SIM_END_OF_MARKET_DATA"

def test_17_initial_mark_uses_close(env):
    _,repo,ps,_,pb=env; p=make_portfolio(ps); pos=make_position(ps,p); active(pb,p); assert repo.get_position(pos.id).current_price==Decimal("80000")

def test_18_next_mark_updates_close(env):
    _,repo,ps,_,pb=env; p=make_portfolio(ps); pos=make_position(ps,p); active(pb,p); pb.next_day(p.id); assert repo.get_position(pos.id).current_price==Decimal("81500")

def test_19_market_value_changes(env):
    _,_,ps,_,pb=env; p=make_portfolio(ps); make_position(ps,p); active(pb,p); r=pb.next_day(p.id); assert r.summary.positions_market_value==Decimal("815000")

def test_20_unrealized_changes(env):
    _,_,ps,_,pb=env; p=make_portfolio(ps); make_position(ps,p); active(pb,p); r=pb.next_day(p.id); assert r.summary.unrealized_pnl==Decimal("15000")

def test_21_equity_changes(env):
    _,_,ps,_,pb=env; p=make_portfolio(ps); make_position(ps,p); active(pb,p); r=pb.next_day(p.id); assert r.summary.total_equity==Decimal("10815000")

def test_22_cash_unchanged(env):
    _,repo,ps,_,pb=env; p=make_portfolio(ps); make_position(ps,p); active(pb,p); pb.next_day(p.id); assert repo.get_portfolio(p.id).cash_balance==Decimal("10000000")

def test_23_realized_unchanged(env):
    _,repo,ps,_,pb=env; p=make_portfolio(ps); make_position(ps,p); active(pb,p); pb.next_day(p.id); assert repo.get_portfolio(p.id).realized_pnl==Decimal("0")

def test_24_two_positions_update(env):
    _,repo,ps,_,pb=env; p=make_portfolio(ps); a=make_position(ps,p); b=make_position(ps,p,"035720","KOSDAQ",2,"50000","50000"); active(pb,p); r=pb.next_day(p.id); assert r.updated_positions==2 and repo.get_position(b.id).current_price==Decimal("51000")

def test_25_closed_excluded(env):
    _,repo,ps,provider,pb=env; p=make_portfolio(ps); pos=make_position(ps,p); repo.raw_execute("UPDATE simulation_position SET status='CLOSED',quantity=0,closed_at=? WHERE id=?",(NOW.isoformat(),pos.id)); active(pb,p); assert provider.calls==[]

def test_26_missing_keeps_last_price(env):
    _,repo,ps,provider,pb=env; p=make_portfolio(ps); pos=make_position(ps,p); active(pb,p); provider.bars.pop(("KOSPI","005930",D2)); pb.next_day(p.id); assert repo.get_position(pos.id).current_price==Decimal("80000")

def test_27_missing_mark_stale(env):
    _,repo,ps,provider,pb=env; p=make_portfolio(ps); pos=make_position(ps,p); s=active(pb,p); provider.bars.pop(("KOSPI","005930",D2)); pb.next_day(p.id); m=SimulationPlaybackStore(repo).get_mark(pos.id); assert m.price_status==PriceStatus.STALE and m.valuation_stale

def test_28_fresh_mark(env):
    _,repo,ps,_,pb=env; p=make_portfolio(ps); pos=make_position(ps,p); active(pb,p); pb.next_day(p.id); m=SimulationPlaybackStore(repo).get_mark(pos.id); assert m.price_status==PriceStatus.FRESH and not m.valuation_stale and m.source_bar_date==D2

def test_29_missing_count(env):
    _,_,ps,provider,pb=env; p=make_portfolio(ps); make_position(ps,p); active(pb,p); provider.bars.pop(("KOSPI","005930",D2)); r=pb.next_day(p.id); assert (r.updated_positions,r.missing_positions)==(0,1)

def test_30_date_step_saved(env):
    _,repo,ps,_,pb=env; p=make_portfolio(ps); active(pb,p); r=pb.next_day(p.id); steps=SimulationPlaybackStore(repo).list_steps(r.session.id); assert len(steps)==1 and steps[0].to_date==D2

def test_31_initial_mark_no_step(env):
    _,repo,ps,_,pb=env; p=make_portfolio(ps); s=active(pb,p); assert SimulationPlaybackStore(repo).list_steps(s.id)==[]

def test_32_advance_one(env):
    _,_,ps,_,pb=env; p=make_portfolio(ps); active(pb,p); assert pb.advance(p.id,1)[-1].current_date==D2

def test_33_advance_three(env):
    _,_,ps,_,pb=env; p=make_portfolio(ps); active(pb,p); rs=pb.advance(p.id,3); assert [r.current_date for r in rs]==[D2,D3,D4]

def test_34_advance_invalid(env):
    _,_,ps,_,pb=env; p=make_portfolio(ps); active(pb,p)
    with pytest.raises(SimulationPlaybackError) as e: pb.advance(p.id,0)
    assert errcode(e)=="SIM_INVALID_ADVANCE_DAYS"

def test_35_move_to_forward(env):
    _,_,ps,_,pb=env; p=make_portfolio(ps); active(pb,p); assert pb.move_to(p.id,D4).current_date==D4

def test_36_move_to_nontrading_rejected(env):
    _,_,ps,_,pb=env; p=make_portfolio(ps); active(pb,p)
    with pytest.raises(SimulationPlaybackError) as e: pb.move_to(p.id,date(2025,1,4))
    assert errcode(e)=="SIM_INVALID_TRADING_DATE"

def test_37_backward_after_trade_rejected(env):
    root,repo,ps,_,pb=env; p=make_portfolio(ps); active(pb,p); pb.next_day(p.id); tr=SimulationTradingService(repo,BaselineRegistry(root/"backend/runtime/baseline")); tr.buy(BuyCommand(portfolio_id=p.id,stock_code="005930",stock_name="삼성전자",market="KOSPI",quantity=1,execution_price=Decimal("81500"),source=PositionSource.MANUAL),now=NOW)
    with pytest.raises(SimulationPlaybackError) as e: pb.previous_day(p.id)
    assert errcode(e)=="SIM_BACKWARD_AFTER_TRADE_NOT_ALLOWED"

def test_38_no_lookahead_exact_date_calls(env):
    _,_,ps,provider,pb=env; p=make_portfolio(ps); make_position(ps,p); active(pb,p); provider.calls.clear(); pb.next_day(p.id); assert provider.calls==[("KOSPI","005930",D2)]

def test_39_ohlcv_preserved(env):
    _,_,ps,_,pb=env; p=make_portfolio(ps); make_position(ps,p); active(pb,p); r=pb.next_day(p.id); b=r.positions[0].bar; assert (b.open,b.high,b.low,b.close,b.volume)==(Decimal("81400"),Decimal("81700"),Decimal("81200"),Decimal("81500"),1000)

def test_40_decimal_precision(env):
    _,_,ps,provider,pb=env; p=make_portfolio(ps); make_position(ps,p,entry="0.1",current="0.1"); provider.bars[("KOSPI","005930",D2)]=HistoricalMarketBar("005930","KOSPI",D2,Decimal("0.2"),Decimal("0.3"),Decimal("0.1"),Decimal("0.2"),1); active(pb,p); assert pb.next_day(p.id).positions[0].current_price==Decimal("0.2")

def test_41_session_not_found(env):
    _,_,ps,_,pb=env; p=make_portfolio(ps)
    with pytest.raises(SimulationPlaybackError) as e: pb.next_day(p.id)
    assert errcode(e)=="SIM_SESSION_NOT_FOUND"

def test_42_portfolio_not_found(env):
    *_,pb=env
    with pytest.raises(SimulationPlaybackError) as e: pb.create_session("missing",start_date=D1)
    assert errcode(e)=="SIM_PORTFOLIO_NOT_FOUND"

def test_43_api_models():
    req=CreateSessionRequest(start_date=D1,end_date=D5); adv=AdvanceRequest(trading_days=5); assert req.start_date==D1 and adv.trading_days==5

def test_44_provider_protocol_shape(env):
    provider=env[3]; assert all(hasattr(provider,n) for n in ("has_trading_day","next_trading_day","previous_trading_day","get_bar"))

def test_45_step_summary_values(env):
    _,repo,ps,_,pb=env; p=make_portfolio(ps); make_position(ps,p); s=active(pb,p); pb.next_day(p.id); step=SimulationPlaybackStore(repo).list_steps(s.id)[0]; assert step.total_equity==Decimal("10815000") and step.cash_balance==Decimal("10000000")

def test_46_migration_preserves_portfolio(env):
    _,repo,ps,_,_=env; p=make_portfolio(ps); before=repo.get_portfolio(p.id); repo.initialize(); assert repo.schema_version()==3 and repo.get_portfolio(p.id)==before

def test_47_migration_preserves_position(env):
    _,repo,ps,_,_=env; p=make_portfolio(ps); pos=make_position(ps,p); repo.initialize(); assert repo.get_position(pos.id)==pos

def test_48_tables_exist(env):
    _,repo,_,_,_=env
    with repo.connect() as c:
        names={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"simulation_session","simulation_date_step","simulation_position_mark_state"} <= names

def test_49_active_unique_db_constraint(env):
    _,repo,ps,_,pb=env; p=make_portfolio(ps); s=active(pb,p)
    with pytest.raises(sqlite3.IntegrityError):
        with repo.connect() as c: c.execute("INSERT INTO simulation_session VALUES(?,?,?,?,?,?,?,?)",("x",p.id,D1.isoformat(),None,D1.isoformat(),"ACTIVE",NOW.isoformat(),NOW.isoformat()))

def test_50_completed_session_allows_new_active(env):
    _,repo,ps,_,pb=env; p=make_portfolio(ps); s=active(pb,p); repo.raw_execute("UPDATE simulation_session SET status='COMPLETED' WHERE id=?",(s.id,)); s2=active(pb,p); assert s2.id!=s.id


class Series:
    def __init__(self, rows): self.rows=rows

class FakeHistoricalStore:
    def __init__(self): self.complete={"20250102","20250103","20250106"}; self.calls=[]
    def latest_complete_date(self,market,kind,key): return key if key in self.complete else None
    def stock_series_many(self,market,codes,start,end):
        self.calls.append((market,tuple(codes),start,end))
        if start!="20250103": return {}
        return {codes[0]:Series({start:{"date":start,"open":"100","high":"120","low":"90","close":"110","volume":"123"}})}

def test_51_real_adapter_calendar():
    p=HistoricalMarketStoreProvider(FakeHistoricalStore()); assert p.has_trading_day(D1) and p.next_trading_day(D2)==D3 and p.previous_trading_day(D3)==D2

def test_52_real_adapter_exact_bar():
    store=FakeHistoricalStore(); p=HistoricalMarketStoreProvider(store); b=p.get_bar("KOSPI","005930",D2); assert b.close==Decimal("110") and store.calls[-1][2:]==("20250103","20250103")

def test_53_real_adapter_krx_market_probe():
    store=FakeHistoricalStore(); p=HistoricalMarketStoreProvider(store); assert p.get_bar("KRX","005930",D2) is not None

def test_54_bad_bar_returns_none():
    class Bad(FakeHistoricalStore):
      def stock_series_many(self,market,codes,start,end): return {codes[0]:Series({start:{"date":start,"open":"x","high":"2","low":"1","close":"2","volume":"1"}})}
    assert HistoricalMarketStoreProvider(Bad()).get_bar("KOSPI","005930",D2) is None

def test_55_external_http_not_imported_by_provider_source():
    import inspect
    import app.simulation.sim3_market_provider as m
    src=inspect.getsource(m); assert "httpx" not in src and "requests" not in src and "aiohttp" not in src
