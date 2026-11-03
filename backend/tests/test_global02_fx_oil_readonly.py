from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.integrations.fred.client import FredApiError
from app.macro.global02_fx_oil import (
    Global02SeriesError, _value, normalize_observations,
    retrospective_relation, validate_series_metadata,
)
from tools.data.analyze_global02_fx_oil import (
    open_krx_readonly, read_krx_context, run_research,
)

FX = "DEXKOUS"
OIL = "DCOILBRENTEU"
START = date(2026, 9, 1)
END = date(2026, 10, 30)


def _meta(series: str):
    if series == FX:
        return {"id": FX, "title": "South Korean Won to U.S. Dollar Spot Exchange Rate",
                "frequency": "Daily", "units": "South Korean Won to One U.S. Dollar",
                "seasonal_adjustment": "Not Seasonally Adjusted",
                "last_updated": "2026-11-02 15:15:00-05:00"}
    return {"id": OIL, "title": "Crude Oil Prices: Brent - Europe",
            "frequency": "Daily", "units": "Dollars per Barrel",
            "seasonal_adjustment": "Not Seasonally Adjusted"}


def _days(count=24, start=START):
    result = []
    d = start
    while len(result) < count:
        if d.weekday() < 5:
            result.append(d)
        d += timedelta(days=1)
    return result


def _db(tmp_path: Path, *, count: int = 24):
    path = tmp_path / "market_history.db"
    days = _days(count)
    holiday = date(2026, 9, 12)  # Saturday between complete market sessions
    with sqlite3.connect(path) as db:
        db.executescript("""
          CREATE TABLE day_status(market TEXT,bas_dd TEXT,kind TEXT,status TEXT,
             PRIMARY KEY (market,bas_dd,kind));
          CREATE TABLE main_index_daily(market TEXT,bas_dd TEXT,row_json TEXT,
             PRIMARY KEY (market,bas_dd));
          CREATE TABLE stock_daily(market TEXT,bas_dd TEXT,stock_code TEXT,row_json TEXT,
             PRIMARY KEY (market,bas_dd,stock_code));
        """)
        for market, code in (("KOSPI","005930"),("KOSDAQ","000250")):
            for day in days:
                k = day.strftime("%Y%m%d")
                position = days.index(day)
                for kind in ("index", "stock"):
                    db.execute("INSERT INTO day_status VALUES (?,?,?,?)",
                               (market,k,kind,"data"))
                db.execute("INSERT INTO main_index_daily VALUES (?,?,?)",
                           (market,k,json.dumps({
                               "date": k,
                               "close": str(2500 + position * 8 if market == "KOSPI"
                                            else 850 + position * 4),
                               "change_rate":"0.1",
                           })))
                db.execute("INSERT INTO stock_daily VALUES (?,?,?,?)",
                           (market,k,code,json.dumps({"date":k,"close":"200"})))
            for kind in ("index", "stock"):
                db.execute("INSERT INTO day_status VALUES (?,?,?,?)",
                           (market,holiday.strftime("%Y%m%d"),kind,"empty"))
    return path,days,holiday


def _rows(days,series):
    values = [str(1350 + i * (1 if i % 3 else -1)) if series == FX
              else str(75 + i * .5) for i in range(len(days))]
    return [
        {"date": d.isoformat(), "value": values[i],
         "realtime_start": "2026-11-02", "realtime_end":"2026-11-02"}
        for i,d in enumerate(days)
    ]


class FakeFred:
    def __init__(self,days,*,wrong_unit=None,error=None):
        self.days=days
        self.wrong_unit=wrong_unit
        self.error=error
        self.series_calls=[]
        self.observation_calls=[]

    def series(self,series):
        self.series_calls.append(series)
        if self.error:
            raise FredApiError("test-only",status_code=self.error)
        metadata = _meta(series)
        if series == self.wrong_unit:
            metadata["units"] = "Index"
        return metadata

    def observations(self,series,**kwargs):
        self.observation_calls.append((series,kwargs))
        return type("Batch",(),{"observations":tuple(_rows(self.days,series))})()


def test_global02_fred_series_units_identity_and_direction_are_strict():
    assert validate_series_metadata(FX,_meta(FX))["direction_if_increasing"] == "KRW_WEAKENS"
    assert validate_series_metadata(OIL,_meta(OIL))["unit"] == "USD_PER_BARREL"
    for series,field,value in (
        (FX,"id","EXKOUS"),
        (FX,"units","U.S. Dollars to One South Korean Won"),
        (OIL,"frequency","Monthly"),
        (OIL,"title","WTI Futures"),
        (FX,"seasonal_adjustment","Seasonally Adjusted"),
    ):
        m=_meta(series)
        m[field]=value
        with pytest.raises(Global02SeriesError):
            validate_series_metadata(series,m)


def test_global02_missing_invalid_and_duplicate_fred_rows_are_not_imputed():
    rows=[
        {"date":"2026-09-01","value":"1340"},
        {"date":"2026-09-02","value":"."},
        {"date":"2026-09-03","value":"1345"},
        {"date":"2026-09-03","value":"1345"},
        {"date":"2026-09-04","value":"-100"},
        {"date":"2026-09-07","value":"NaN"},
    ]
    normal=normalize_observations(FX,rows,_meta(FX),start=START,end=END,
                                  retrieved_at_utc="2026-11-03T00:00:00Z")
    assert normal["public"]["observation_count"]==2
    assert normal["public"]["missing_count"]==3
    assert normal["public"]["duplicate_count"]==1
    assert normal["public"]["source_published_at_utc"] is None
    assert normal["public"]["historical_decision_eligible"] is False
    assert normal["points"][1]["previous_date"]==date(2026,9,1)
    assert normal["points"][1]["previous_gap_calendar_days"]==2
    assert "value" not in str(normal["public"])
    rows[3]["value"]="1346"
    with pytest.raises(Global02SeriesError,match="DUPLICATE_DATE_CONFLICT"):
        normalize_observations(FX,rows,_meta(FX),start=START,end=END,
                               retrieved_at_utc="2026-11-03T00:00:00Z")


def test_global02_no_optin_no_provider_calls_or_krx_database_access(tmp_path: Path):
    fake=FakeFred(_days())
    out=run_research(start=START,end=END,confirm_personal_research=False,
                     metadata_only=False,db_path=tmp_path/"missing.db",client=fake)
    assert out["status"]=="RIGHTS_UNVERIFIED"
    assert out["raw_provider_rows_in_output"] is False
    assert out["jev_input_approved"] is False
    assert fake.series_calls==fake.observation_calls==[]


def test_global02_krx_readonly_ignore_holiday_and_prevent_writes(tmp_path: Path):
    path,days,holiday=_db(tmp_path)
    before=(path.stat().st_mtime_ns,path.stat().st_size)
    with open_krx_readonly(path) as conn:
        context=read_krx_context(conn,start=START,end=END)
        assert context["status"]=="READY"
        assert context["ignored_empty_marker_days"]==1
        assert context["verified_common_sessions"]==len(days)
        assert context["matched_return_ready_sessions"]==len(days)-1
        assert context["daily_returns"][days[1].isoformat()]["KOSPI"]>0
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("UPDATE day_status SET status='empty'")
    assert (path.stat().st_mtime_ns,path.stat().st_size)==before


def test_global02_partial_trading_data_and_invalid_index_never_pass(tmp_path: Path):
    path,days,holiday=_db(tmp_path)
    with sqlite3.connect(path) as con:
        con.execute("UPDATE day_status SET status='data' WHERE bas_dd=? AND"
                    " market='KOSPI' AND kind='index'",(holiday.strftime("%Y%m%d"),))
    with open_krx_readonly(path) as conn:
        result=read_krx_context(conn,start=START,end=END)
    assert result["status"]=="DATA_INSUFFICIENT"
    assert result["reason"]=="PARTIAL_KRX_MARKET_DATA_MARKERS"
    with sqlite3.connect(path) as con:
        con.execute("UPDATE day_status SET status='empty' WHERE bas_dd=? AND"
                    " market='KOSPI' AND kind='index'",(holiday.strftime("%Y%m%d"),))
        con.execute("UPDATE main_index_daily SET row_json=?"
                    " WHERE market='KOSDAQ' AND bas_dd=?",
                    (json.dumps({"date":days[8].strftime("%Y%m%d"),"close":"0"}),
                     days[8].strftime("%Y%m%d")))
    with open_krx_readonly(path) as conn:
        result=read_krx_context(conn,start=START,end=END)
    assert result["reason"]=="KRX_PHYSICAL_INDEX_OR_STOCK_ROWS_INVALID"


def test_global02_real_existing_krx_fake_fred_end_to_end_aggregate_only(tmp_path: Path):
    path,days,_=_db(tmp_path)
    fake=FakeFred(days)
    baseline=(path.stat().st_mtime_ns,path.stat().st_size)
    result=run_research(
        start=START,end=END,confirm_personal_research=True,metadata_only=False,
        db_path=path,client=fake,retrieved_at_utc="2026-11-03T00:00:00+00:00")
    assert result["status"]=="RETROSPECTIVE_DESCRIPTIVE_ONLY"
    assert len(fake.observation_calls)==2
    assert len(fake.series_calls)==2
    assert result["krx"]["verified_common_sessions"]==24
    for name in (FX,OIL):
        group=result["relations"][name]
        assert group["paired_sessions"]==23
        assert group["independent_pit_verified_pairs"]==0
        assert group["claim_scope"]=="RETROSPECTIVE_ASSOCIATION_NOT_CAUSATION"
        assert group["groups"]["fx_or_oil_up"]["count"]>=1
    assert result["series"][FX]["source_published_at_utc"] is None
    assert result["production_decision_approved"] is False
    assert result["ai_transfer_approved"] is False
    assert result["file_writes"]==0
    assert result["db_writes"]==0
    assert "1350" not in json.dumps(result)
    assert (path.stat().st_mtime_ns,path.stat().st_size)==baseline


def test_global02_metadata_only_does_not_read_observations(tmp_path: Path):
    path,days,_=_db(tmp_path)
    fake=FakeFred(days)
    result=run_research(start=START,end=END,confirm_personal_research=True,
                        metadata_only=True,db_path=path,client=fake)
    assert result["status"]=="METADATA_VERIFIED"
    assert fake.series_calls==[FX,OIL]
    assert fake.observation_calls==[]
    assert result["series"][FX]["rights_status"].startswith("PERSONAL_NONCOMMERCIAL")


@pytest.mark.parametrize("code,expected",[(401,"FRED_AUTH_FAILED"),
                                          (403,"FRED_AUTH_FAILED"),
                                          (429,"FRED_RATE_LIMITED"),
                                          (500,"FRED_PROVIDER_ERROR")])
def test_global02_provider_failures_are_sanitized(tmp_path: Path,code:int,expected:str):
    path,days,_=_db(tmp_path)
    fake=FakeFred(days,error=code)
    result=run_research(start=START,end=END,confirm_personal_research=True,
                        metadata_only=False,db_path=path,client=fake)
    assert result["status"]=="SOURCE_UNAVAILABLE"
    assert result["series"][FX]["reason"]==expected
    assert "api_key" not in json.dumps(result)
    assert "test-only" not in json.dumps(result)


def test_global02_missing_market_database_never_created(tmp_path: Path):
    file=tmp_path/"not-created.db"
    result=run_research(start=START,end=END,confirm_personal_research=True,
                        metadata_only=False,db_path=file,client=FakeFred(_days()))
    assert result["status"]=="DATA_INSUFFICIENT"
    assert not file.exists()


def test_global02_retrospective_match_denies_pit_even_on_same_date():
    metadata=_meta(FX)
    values=normalize_observations(FX,_rows(_days(6),FX),metadata,
                                  start=START,end=END,
                                  retrieved_at_utc="2026-11-03T00:00:00Z")
    domestic={"daily_returns":{
        d.isoformat():{"KOSPI":1,"KOSDAQ":-1} for d in _days(6)
    }}
    result=retrospective_relation(values,domestic,series_id=FX)
    assert result["paired_sessions"]==5
    assert result["independent_pit_verified_pairs"]==0
    assert result["historical_decision_eligible"] is False
    assert result["risk_gate_input_approved"] is False
