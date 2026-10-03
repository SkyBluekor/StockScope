from __future__ import annotations

import hashlib
import itertools
import json
import math
import bisect
from collections import Counter
from datetime import date
from decimal import Decimal
from fractions import Fraction
from statistics import median
from typing import Any

from app.macro.r4_contract import (
    ARITHMETIC_PROFILE_ID, DIAGNOSTIC_SCHEMA_ID, EXPECTED_DATASET_HASH, EXPECTED_DATASET_ID,
    METHOD_ID, content_hash,
)
from app.macro.r4_lattice import midpoint_median, raw_mad, median_set

HORIZONS = (1, 5, 10)
FIDS = {h: f"delta_bp_{h}obs" for h in HORIZONS}
CANONICAL_LEGACY = {"coordinate_m": [1, 5, 21], "lag_cutoff_L": 10, "bandwidth_b": 22, "effective_ell": 43}
HISTORICAL_R3_LEGACY = {"coordinate_m": [1, 5, 10], "lag_cutoff_L": 10, "bandwidth_b": 22, "effective_ell": 43}
NPCP_REFERENCE_COMMIT = "d602c9b50730560c947fb776bfd3c7b4f4905bf8"
NPCP_LNOPT_BLOB = "b9c92dcf245106b0a122035214e269a05fbe392f"
LEGACY_PROVENANCE_RESOLUTION = "REFERENCE_SPEC_TRANSCRIPTION_ERROR_LOG_BASE"


class R4DiagnosticError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _features(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {x["feature_id"]: x for x in row["features"]}


def _d(value: Any) -> Decimal:
    out = Decimal(str(value))
    if not out.is_finite():
        raise R4DiagnosticError("NONFINITE_INPUT", "nonfinite numeric input")
    return out


def validate_lineage(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    if dataset.get("dataset_id") != EXPECTED_DATASET_ID or dataset.get("dataset_hash") != EXPECTED_DATASET_HASH:
        raise R4DiagnosticError("LINEAGE_MISMATCH", "unexpected Development dataset identity")
    manifest = dataset.get("manifest") or {}
    expected = {
        "analysis_row_count": 1999, "provider": "FRED", "provider_series_id": "DGS10",
        "series_id": "US_10Y_CONSTANT_MATURITY_YIELD", "vintage_id": "2023-12-29",
        "observation_start": "2016-01-04", "observation_end": "2023-12-29",
        "warmup_count": 10, "warmup_required": 10, "split_role": "DEVELOPMENT",
        "usage_scope": "REFERENCE_RESEARCH_ONLY", "historical_pit_eligible_count": 0,
        "production_decision_approved": False,
    }
    for key, val in expected.items():
        if manifest.get(key) != val:
            raise R4DiagnosticError("LINEAGE_MISMATCH", f"manifest.{key} mismatch")
    rows = list(dataset.get("rows") or [])
    if len(rows) != 1999:
        raise R4DiagnosticError("LINEAGE_MISMATCH", "analysis row count mismatch")
    row_hashes = []
    for row in rows:
        fp = {"contract_version": row["feature_contract_version"], "series_id": row["series_id"], "features": row["features"]}
        if _hash(fp) != row["feature_set_hash"]:
            raise R4DiagnosticError("LINEAGE_MISMATCH", "feature hash mismatch")
        ident = {
            "split_role": row["split_role"], "series_id": row["series_id"], "vintage_id": row["vintage_id"],
            "observation_key": row["observation_key"], "observation_date": row["observation_date"],
            "normalized_hash": row["normalized_hash"], "feature_contract_version": row["feature_contract_version"],
            "feature_set_hash": row["feature_set_hash"],
        }
        rh = _hash(ident)
        if rh != row["row_hash"]:
            raise R4DiagnosticError("LINEAGE_MISMATCH", "row hash mismatch")
        row_hashes.append(rh)
    if _hash({"manifest": manifest, "row_hashes": row_hashes}) != EXPECTED_DATASET_HASH:
        raise R4DiagnosticError("LINEAGE_MISMATCH", "canonical dataset hash mismatch")
    return rows


def reconstruct(rows: list[dict[str, Any]]) -> tuple[dict[int, str], dict[int, str], dict[int, Decimal]]:
    refs: dict[int, str] = {}; dates: dict[int, str] = {}; levels: dict[int, Decimal] = {}
    def put(target: dict[int, Any], p: int, value: Any) -> None:
        if p in target and target[p] != value:
            raise R4DiagnosticError("NATIVE_POSITION_INCOMPLETE", "native position conflict")
        target[p] = value
    for i, row in enumerate(rows):
        f = _features(row); rate = f["rate_level_pct"]
        ref, day, level = str(rate["current_observation_ref"]), str(rate["current_observation_date"]), _d(rate["value"])
        if ref != row["normalized_hash"] or day != row["observation_date"]:
            raise R4DiagnosticError("NATIVE_POSITION_INCOMPLETE", "current identity mismatch")
        put(refs, i, ref); put(dates, i, day); put(levels, i, level)
        for h, fid in FIDS.items():
            x = f[fid]
            if x["status"] != "AVAILABLE" or int(x["observation_distance"]) != h:
                raise R4DiagnosticError("JOINT_ALIGNMENT_INVALID", f"{fid} unavailable")
            p = i - h
            put(refs, p, str(x["baseline_observation_ref"])); put(dates, p, str(x["baseline_observation_date"])); put(levels, p, level - _d(x["value"])/100)
    expected = list(range(-10, len(rows)))
    if sorted(refs) != expected or len(set(refs.values())) != len(refs):
        raise R4DiagnosticError("NATIVE_POSITION_INCOMPLETE", "native map incomplete")
    parsed = [date.fromisoformat(dates[p]) for p in expected]
    if any(a >= b for a,b in zip(parsed, parsed[1:])):
        raise R4DiagnosticError("NATIVE_POSITION_INCOMPLETE", "chronology not strictly increasing")
    return refs, dates, levels


def validate_representation(rows: list[dict[str, Any]], levels: dict[int, Decimal]) -> int:
    count = 0
    for i,row in enumerate(rows):
        f = _features(row)
        for h,fid in FIDS.items():
            actual = _d(f[fid]["value"])
            direct = (levels[i]-levels[i-h])*100
            telescoped = sum((levels[p]-levels[p-1])*100 for p in range(i-h+1,i+1))
            if actual != direct or actual != telescoped:
                raise R4DiagnosticError("REPRESENTATION_MISMATCH", "W to X mismatch")
            count += 1
    return count


def _series(rows: list[dict[str, Any]]) -> dict[int, list[Decimal]]:
    return {h: [_d(_features(r)[FIDS[h]]["value"]) for r in rows] for h in HORIZONS}


def _frac_text(x: Fraction) -> str:
    return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"


def _finite_summary(values: list[Decimal]) -> dict[str, Any]:
    fr = [Fraction(v) for v in values]
    lo,hi = median_set(fr); mid = midpoint_median(fr); mad = raw_mad(fr)
    c = Counter(values)
    def left_count(v: Fraction) -> int: return sum(1 for x in fr if x < v)
    def le_count(v: Fraction) -> int: return sum(1 for x in fr if x <= v)
    return {
        "count": len(values), "unique_count": len(c),
        "q_minus_half": _frac_text(lo), "q_plus_half": _frac_text(hi), "midpoint_median": _frac_text(mid),
        "raw_mad": _frac_text(mad), "median_tie_count": sum(1 for x in fr if x == mid) if mid.denominator == 1 else 0,
        "left_count_at_q_minus": left_count(lo), "le_count_at_q_minus": le_count(lo), "le_count_at_q_plus": le_count(hi),
        "frequency_table": [[str(k),v] for k,v in sorted(c.items())],
    }


def _zero_scale(values: list[Decimal], n0: int) -> list[int]:
    ordered: list[Decimal] = []
    out: list[int] = []
    for n, value in enumerate(values, start=1):
        bisect.insort(ordered, value)
        if n < n0 or n >= len(values):
            continue
        if n % 2:
            med = ordered[n//2]
            left=bisect.bisect_left(ordered,med); right=bisect.bisect_right(ordered,med)
            if right-left >= (n+1)//2: out.append(n)
        else:
            lo=ordered[n//2-1]; hi=ordered[n//2]
            if lo==hi:
                left=bisect.bisect_left(ordered,lo); right=bisect.bisect_right(ordered,lo)
                if right-left >= n//2+1: out.append(n)
    return out


def _ecdf_sup(a: list[Decimal], b: list[Decimal]) -> Fraction:
    supports=sorted(set(a)|set(b)); ca=Counter(a); cb=Counter(b); na=len(a); nb=len(b); A=B=0; best=Fraction(0)
    for x in supports:
        A += ca[x]; B += cb[x]
        best=max(best, abs(Fraction(A,na)-Fraction(B,nb)))
    return best


def _bins(values: dict[int,list[Decimal]]) -> list[dict[str,Any]]:
    n=len(next(iter(values.values()))); out=[]
    for j in range(1,11):
        a=(j-1)*n//10; b=j*n//10
        item={"bin":j,"start_index":a,"end_index_exclusive":b,"horizons":{}}
        for h in HORIZONS:
            xs=values[h][a:b]
            item["horizons"][str(h)]={"summary":_finite_summary(xs),"sup_distance_to_full":_frac_text(_ecdf_sup(xs,values[h]))}
        out.append(item)
    return out


def _int_bp(xs: list[Decimal]) -> list[int]:
    out=[]
    for x in xs:
        if x != x.to_integral_value(): raise R4DiagnosticError("OBSERVED_LAW_CONTRACT_MISMATCH","off-grid basis-point value")
        out.append(int(x))
    return out


def _lag_cov_raw(xs: list[Decimal]) -> list[str]:
    vals=_int_bp(xs); n=len(vals); total=sum(vals)
    pref=[0]
    for x in vals: pref.append(pref[-1]+x)
    out=[]
    for r in range(1,n):
        pair=sum(vals[i]*vals[i+r] for i in range(n-r)); left=pref[n-r]; right=total-pref[r]
        num=n*n*pair - n*total*(left+right) + (n-r)*total*total
        out.append(_frac_text(Fraction(num,n*n*n)))
    return out


def _indicator_covariances(xs: list[Decimal]) -> dict[str,list[str]]:
    n=len(xs); supports=sorted(set(xs)); out={}
    for threshold in supports:
        bits=0; pref=[0]
        for i,x in enumerate(xs):
            if x <= threshold: bits |= 1<<i
            pref.append(pref[-1]+(1 if x<=threshold else 0))
        total=pref[-1]; mean=Fraction(total,n); cov=[]
        for r in range(1,n):
            pair=(bits & (bits>>r)).bit_count()
            left=pref[n-r]; right=total-pref[r]
            value=(Fraction(pair)-mean*(left+right)+Fraction(n-r)*mean*mean)/n
            cov.append(_frac_text(value))
        out[str(threshold)] = cov
    return out


def _rank_average(xs: list[Decimal]) -> list[float]:
    indexed=sorted((x,i) for i,x in enumerate(xs)); ranks=[0.0]*len(xs); p=0
    while p<len(indexed):
        q=p+1
        while q<len(indexed) and indexed[q][0]==indexed[p][0]: q+=1
        avg=((p+1)+q)/2.0
        for k in range(p,q): ranks[indexed[k][1]]=avg
        p=q
    return ranks


def _acf(xs: list[float], lagmax: int) -> list[float]:
    n=len(xs); m=sum(xs)/n; den=sum((x-m)**2 for x in xs)/n
    if den==0: return [float('nan')]*lagmax
    return [sum((xs[i]-m)*(xs[i+r]-m) for i in range(n-r))/n/den for r in range(1,lagmax+1)]


def _mval(rho: list[float], kn: int, crit: float) -> int:
    for j in range(0,len(rho)-kn+1):
        if sum(abs(x)<crit for x in rho[j:j+kn])==kn: return j+1
    sig=[i+1 for i,x in enumerate(rho) if abs(x)>crit]
    return (sig[0] if len(sig)==1 else max(sig)) if sig else 1


def _binary_ccov(mask_a: int, total_a: int, pref_a: list[int], mask_b: int, total_b: int, pref_b: list[int], n: int, lag: int) -> float:
    ma=total_a/n; mb=total_b/n
    if lag >= 0:
        pairs=(mask_a & (mask_b >> lag)).bit_count()
        suma=pref_a[n-lag]; sumb=total_b-pref_b[lag]; count=n-lag
    else:
        r=-lag; pairs=((mask_a >> r) & mask_b).bit_count()
        suma=total_a-pref_a[r]; sumb=pref_b[n-r]; count=n-r
    return (pairs-ma*sumb-mb*suma+count*ma*mb)/n


def _selector_profile(cols: list[list[float]], *, log_base: str) -> dict[str, Any]:
    n=len(cols[0])
    if log_base == "LOG10":
        log_n=math.log10(n)
    elif log_base == "NATURAL_LOG":
        log_n=math.log(n)
    else:
        raise ValueError("UNKNOWN_LOG_BASE")
    kn=max(5, math.ceil(log_n)); lagmax=math.ceil(math.sqrt(n))+kn; crit=1.96*math.sqrt(log_n/n)
    coordinate_m=[_mval(_acf(col,lagmax),kn,crit) for col in cols]
    return {"log_base":log_base,"k_n":kn,"lag_max":lagmax,"rho_crit":format(crit,'.15g'),"coordinate_m":coordinate_m,"lag_cutoff_L":2*int(median(coordinate_m))}


def legacy_r2_audit(values: dict[int,list[Decimal]]) -> dict[str,Any]:
    n=len(values[1]); cols=[[float(x) for x in values[h]] for h in HORIZONS]
    selector=_selector_profile(cols,log_base="LOG10")
    historical_selector=_selector_profile(cols,log_base="NATURAL_LOG")
    m=selector["coordinate_m"]; L=selector["lag_cutoff_L"]; lagmax=selector["lag_max"]
    ranks=[_rank_average(values[h]) for h in HORIZONS]; U=[[r/(n+1) for r in col] for col in ranks]
    grid=[i/6 for i in range(1,6)]; points=list(itertools.product(grid, repeat=3)); ng=len(points)
    binary=[]
    for g in points:
        mask=0; pref=[0]
        for i in range(n):
            bit=(U[0][i]<=g[0] and U[1][i]<=g[1] and U[2][i]<=g[2])
            if bit: mask |= 1<<i
            pref.append(pref[-1]+int(bit))
        binary.append((mask,pref[-1],pref))
    lags=list(range(-lagmax,lagmax+1)); ft=[min(max((1-abs(lag/L))/(1-0.5),0),1) for lag in lags]
    sigma_sq=0.0; diag_sum=0.0; K_sq=0.0
    for i in range(ng):
        ma,ta,pa=binary[i]
        for j in range(ng):
            mb,tb,pb=binary[j]
            sig=0.0; kval=0.0
            for w,lag in zip(ft,lags):
                if w==0: continue
                cov=_binary_ccov(ma,ta,pa,mb,tb,pb,n,lag)
                sig += w*cov; kval += w*(lag**2)*cov
            sigma_sq += sig*sig; K_sq += kval*kval
            if i==j: diag_sum += sig
    mean_sigma_sq=sigma_sq/(ng*ng); mean_k_sq=K_sq/(ng*ng); mean_diag=diag_sum/ng
    gamma2=495.136227/4*mean_k_sq; delta=0.3723388234*(mean_diag**2+mean_sigma_sq)
    if not math.isfinite(gamma2) or not math.isfinite(delta) or delta<=0: raise R4DiagnosticError("LEGACY_R2_PROFILE_MISMATCH","legacy estimator nonfinite")
    ell=(4*gamma2/delta*n)**0.2; b=round((ell+1)/2); eff=2*b-1
    actual={"coordinate_m":m,"lag_cutoff_L":L,"bandwidth_b":b,"effective_ell":eff,"gamma_squared":format(gamma2,'.15g'),"delta":format(delta,'.15g'),"ell_opt":format(ell,'.15g'),"rounding_mode":"ROUND_TO_NEAREST_TIES_TO_EVEN","status":"LEGACY_REPRODUCTION_ONLY","selector_profile":selector,"historical_natural_log_selector":historical_selector,"reference_identity":{"repository":"cran/npcp","commit":NPCP_REFERENCE_COMMIT,"path":"R/lnOpt.R","blob":NPCP_LNOPT_BLOB,"formula":"kn=max(5,ceiling(log10(n))); rho.crit=1.96*sqrt(log10(n)/n)"},"provenance_resolution":{"classification":LEGACY_PROVENANCE_RESOLUTION,"historical_record_preserved":True,"canonical_log_base":"LOG10","historical_log_base":"NATURAL_LOG"}}
    actual["canonical_reference_match"] = all(actual[k]==v for k,v in CANONICAL_LEGACY.items())
    actual["historical_record_match"] = all(actual[k]==v for k,v in HISTORICAL_R3_LEGACY.items())
    actual["historical_variant_reproduced"] = historical_selector["coordinate_m"] == HISTORICAL_R3_LEGACY["coordinate_m"] and historical_selector["lag_cutoff_L"] == HISTORICAL_R3_LEGACY["lag_cutoff_L"]
    return actual


def _cross_lag_covariances(a: list[Decimal], b: list[Decimal]) -> list[str]:
    aa=_int_bp(a); bb=_int_bp(b); n=len(aa); ta=sum(aa); tb=sum(bb)
    pa=[0]; pb=[0]
    for x in aa: pa.append(pa[-1]+x)
    for x in bb: pb.append(pb[-1]+x)
    out=[]
    for r in range(0,n):
        pair=sum(aa[i]*bb[i+r] for i in range(n-r)); suma=pa[n-r]; sumb=tb-pb[r]
        num=n*n*pair - n*(ta*sumb+tb*suma) + (n-r)*ta*tb
        out.append(_frac_text(Fraction(num,n*n*n)))
    return out


def build_dev_diagnostic(dataset: dict[str,Any], *, transport_digest: str, design_hash: str, input_allowlist_id: str, isolation_audit_id: str, clean_isolation_certified: bool) -> dict[str,Any]:
    if not clean_isolation_certified:
        raise R4DiagnosticError("ISOLATION_NOT_CERTIFIED","clean execution evidence is required")
    rows=validate_lineage(dataset); refs,dates,levels=reconstruct(rows); comparisons=validate_representation(rows,levels); values=_series(rows); n=len(rows); n0=(n+9)//10
    lattice=[]
    for h in HORIZONS:
        off=[str(x) for x in values[h] if x != x.to_integral_value()]
        if off: raise R4DiagnosticError("OBSERVED_LAW_CONTRACT_MISMATCH","off-grid basis-point value")
        lattice.append({"horizon":h,"off_grid_count":0,"summary":_finite_summary(values[h])})
    zero={str(h):_zero_scale(values[h],n0) for h in HORIZONS}
    if any(zero.values()): raise R4DiagnosticError("NON_COMPUTABLE_ZERO_SCALE","zero MAD in approved domain")
    legacy=legacy_r2_audit(values)
    failure_codes=[]
    if not legacy["canonical_reference_match"]: failure_codes.append("LEGACY_R2_CANONICAL_MISMATCH")
    native_map_hash=content_hash([[p,refs[p],dates[p],str(levels[p])] for p in sorted(refs)])
    alignment_hash=content_hash([[rows[i]["observation_date"],*[str(values[h][i]) for h in HORIZONS]] for i in range(n)])
    source_scope={"development_only":True,"input_allowlist_id":input_allowlist_id,"isolation_audit_id":isolation_audit_id,"clean_isolation_certified":True}
    source_scope_hash=content_hash(source_scope)
    base={
        "schema_id":DIAGNOSTIC_SCHEMA_ID,"design_hash":design_hash,
        "source":{"dataset_id":EXPECTED_DATASET_ID,"canonical_dataset_hash":EXPECTED_DATASET_HASH,"canonicalization_version":"STOCKSCOPE_CONTENT_HASH_V1","transport_digest":transport_digest,"native_map_hash":native_map_hash},
        "scope":source_scope,
        "representation":{"units":"BASIS_POINT","horizon_order":[1,5,10],"n":n,"warmup_rule":"10_NATIVE_OBSERVATIONS","alignment_hash":alignment_hash},
        "domain":{"domain_id":"R2A_CANDIDATE_DOMAIN_V1","lower_bound":n0,"upper_anchor":n-1},
        "diagnostics":{"lineage_checks":["CANONICAL_DATASET_IDENTITY_VERIFIED"],"native_checks":["NATIVE_MAP_COMPLETE","STRICT_DATE_ORDER"],"representation_checks":[f"EXACT_COMPARISONS:{comparisons}"],"lattice_counts":lattice,"joint_unique_count":len(set(zip(values[1],values[5],values[10]))),"median_quantile_counts":[x["summary"] for x in lattice],"mad_diagnostics":[{"horizon":h,"zero_scale_anchor_count":len(zero[str(h)])} for h in HORIZONS],"zero_scale_mask":zero,"chronological_bin_summaries":_bins(values),"raw_coordinate_lag_covariances":{str(h):_lag_cov_raw(values[h]) for h in HORIZONS},"cross_horizon_lag_covariances":{f"{a}->{b}":_cross_lag_covariances(values[a],values[b]) for a,b in ((1,5),(1,10),(5,10))},"indicator_lag_covariances":{str(h):_indicator_covariances(values[h]) for h in HORIZONS},"legacy_r2_profile_audit":legacy,"new_calibration_contract":{"span_set":"ALL_INTEGERS_1_THROUGH_N","span_count":n,"covariance_kernel":"PARZEN_COVARIANCE_V1","centering":"FULL_SAMPLE_EMPIRICAL","coupling":"SHARED_GAUSSIAN_VECTOR_PER_REPLICATE","symbolic_contract_verified":True,"stochastic_computation_performed":False}},
        "arithmetic_profile_id":ARITHMETIC_PROFILE_ID,"computation_status":"COMPLETE_WITH_BLOCKERS" if failure_codes else "COMPLETE","failure_codes":failure_codes,
    }
    return {**base,"source_scope_hash":source_scope_hash,"semantic_payload_hash":content_hash(base)}
