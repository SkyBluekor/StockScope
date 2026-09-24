from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
import pytest

from app.holdings import HoldingsCatalog, PositionLifecycleService
from app.holdings.management import HoldingManagementService, HoldingsManagementError

T0 = "2026-09-24T09:00:00+09:00"
T1 = "2026-09-24T10:00:00+09:00"
T2 = "2026-09-24T11:00:00+09:00"
T3 = "2026-09-24T12:00:00+09:00"


def _market(path, close="100"):
    with sqlite3.connect(path) as conn:
        conn.executescript("""
        CREATE TABLE day_status(market TEXT,bas_dd TEXT,kind TEXT,status TEXT);
        CREATE TABLE stock_daily(market TEXT,bas_dd TEXT,stock_code TEXT,row_json TEXT);
        """)
        payload={"date":"2026-09-24","open":close,"high":close,"low":close,"close":close,"volume":"1000"}
        conn.execute("INSERT INTO day_status VALUES('KOSPI','20260924','stock','data')")
        conn.execute("INSERT INTO stock_daily VALUES('KOSPI','20260924','005930',?)",(json.dumps(payload),))


def _env(tmp_path, close="100"):
    hdb=tmp_path/"h.db"; mdb=tmp_path/"m.db"; _market(mdb,close)
    c=HoldingsCatalog(hdb); c.initialize(); life=PositionLifecycleService(c)
    a=c.create_position_account(provider="MANUAL",account_kind="MANUAL",display_name="수동 기록")
    opened=life.register_initial_holding(market="KOSPI",ticker="005930",name="삼성전자",position_account_id=a.id,quantity="10",average_price="100",effective_at=T0)
    return c,life,a,opened,mdb


def _rev(c, stock_id, fp, stop, t1="120", t2="130", action="READY", computed="2026-09-24T00:00:00+00:00"):
    day=c.get_or_create_analysis_day(monitored_stock_id=stock_id,market_date="2026-09-24")
    r=c.append_analysis_revision(analysis_day_id=day.id,input_fingerprint=fp,strategy_key="trend_following",action_state=action,risk_state="READY",reference_price="100",stop_price=stop,target1_price=t1,target2_price=t2,scanner_version="test",analysis_engine_version="test",policy_version="test",source_versions={},snapshot={},computed_at=computed)
    c.promote_current_revision(analysis_day_id=day.id,revision_id=r.id)
    return r


def test_planless_position_and_explicit_apply(tmp_path):
    c,_,_,opened,mdb=_env(tmp_path); s=HoldingManagementService(c,market_store_db=mdb)
    assert s.build(opened.stock_id)["positions"][0]["management_state"]=="NO_ACTIVE_PLAN"
    r=_rev(c,opened.stock_id,"r1","90")
    plan=s.apply_analysis_plan(position_id=opened.position.id,analysis_revision_id=r.id,applied_at=T1)
    assert plan.plan_version==1 and plan.status=="ACTIVE" and plan.stop_price==Decimal("90")


def test_new_revision_is_proposal_then_versions(tmp_path):
    c,_,_,opened,mdb=_env(tmp_path); s=HoldingManagementService(c,market_store_db=mdb)
    r1=_rev(c,opened.stock_id,"r1","90"); p1=s.apply_analysis_plan(position_id=opened.position.id,analysis_revision_id=r1.id,applied_at=T1)
    r2=_rev(c,opened.stock_id,"r2","95",t1="125",t2="135")
    view=s.build(opened.stock_id)["positions"][0]
    assert view["active_plan"]["plan_id"]==p1.id and view["proposal"]["analysis_revision_id"]==r2.id
    p2=s.apply_analysis_plan(position_id=opened.position.id,analysis_revision_id=r2.id,applied_at=T2)
    assert p2.plan_version==2 and [p.status for p in s.list_plans(opened.position.id)]==["SUPERSEDED","ACTIVE"]


def test_stop_loosening_blocked_and_no_trade_does_not_auto_close(tmp_path):
    c,_,_,opened,mdb=_env(tmp_path); s=HoldingManagementService(c,market_store_db=mdb)
    r1=_rev(c,opened.stock_id,"r1","90"); p=s.apply_analysis_plan(position_id=opened.position.id,analysis_revision_id=r1.id,applied_at=T1)
    low=_rev(c,opened.stock_id,"r2","80",action="NO_TRADE")
    assert s.build(opened.stock_id)["positions"][0]["active_plan"]["plan_id"]==p.id
    with pytest.raises(HoldingsManagementError) as exc:
        s.apply_analysis_plan(position_id=opened.position.id,analysis_revision_id=low.id,applied_at=T2)
    assert exc.value.code=="HOLD_PLAN_STOP_LOOSENING_BLOCKED"


def test_buy_partial_sell_preserve_full_sell_closes(tmp_path):
    c,life,a,opened,mdb=_env(tmp_path); s=HoldingManagementService(c,market_store_db=mdb)
    r=_rev(c,opened.stock_id,"r1","90"); p=s.apply_analysis_plan(position_id=opened.position.id,analysis_revision_id=r.id,applied_at=T1)
    life.record_buy(monitored_stock_id=opened.stock_id,position_account_id=a.id,quantity="2",unit_price="105",effective_at=T2)
    assert s.get_active_plan(opened.position.id).id==p.id
    life.record_sell(position_id=opened.position.id,quantity="1",unit_price="110",effective_at=T3)
    assert s.get_active_plan(opened.position.id).id==p.id
    life.record_sell(position_id=opened.position.id,quantity="11",unit_price="110",effective_at="2026-09-24T13:00:00+09:00")
    assert s.get_active_plan(opened.position.id) is None
    assert s.list_plans(opened.position.id)[0].status=="CLOSED"


def test_zero_correction_closes_without_sell_and_rebuy_has_no_plan(tmp_path):
    c,life,a,opened,mdb=_env(tmp_path); s=HoldingManagementService(c,market_store_db=mdb)
    r=_rev(c,opened.stock_id,"r1","90"); s.apply_analysis_plan(position_id=opened.position.id,analysis_revision_id=r.id,applied_at=T1)
    life.record_correction(position_id=opened.position.id,corrected_quantity="0",corrected_average_price="100",effective_at=T2,note="종료 정정")
    assert s.get_active_plan(opened.position.id) is None
    assert not any(e.event_type=="SELL" for e in c.list_position_events(opened.position.id))
    rebuy=life.record_buy(monitored_stock_id=opened.stock_id,position_account_id=a.id,quantity="3",unit_price="105",effective_at=T3)
    assert rebuy.position.id!=opened.position.id and s.get_active_plan(rebuy.position.id) is None


@pytest.mark.parametrize(("close","state"),[("85","STOP_BREACHED"),("100","WITHIN_PLAN"),("121","TARGET1_REACHED"),("131","TARGET2_REACHED")])
def test_management_states(tmp_path,close,state):
    c,_,_,opened,mdb=_env(tmp_path,close); s=HoldingManagementService(c,market_store_db=mdb)
    r=_rev(c,opened.stock_id,"r1","90"); s.apply_analysis_plan(position_id=opened.position.id,analysis_revision_id=r.id,applied_at=T1)
    assert s.build(opened.stock_id)["positions"][0]["management_state"]==state


def test_missing_price_keeps_plan_and_future_revision_rejected(tmp_path):
    c,_,_,opened,_=_env(tmp_path); s=HoldingManagementService(c,market_store_db=tmp_path/"missing.db")
    r=_rev(c,opened.stock_id,"r1","90"); p=s.apply_analysis_plan(position_id=opened.position.id,analysis_revision_id=r.id,applied_at=T1)
    assert s.build(opened.stock_id)["positions"][0]["management_state"]=="DATA_UNAVAILABLE"
    assert s.get_active_plan(opened.position.id).id==p.id
    future=_rev(c,opened.stock_id,"future","95",computed="2026-09-25T00:00:00+00:00")
    with pytest.raises(HoldingsManagementError) as exc:
        s.apply_analysis_plan(position_id=opened.position.id,analysis_revision_id=future.id,applied_at=T2)
    assert exc.value.code=="HOLD_PLAN_REVISION_FROM_FUTURE"
