import sys, types
from enum import Enum

class _StrategyName(str, Enum):
    TREND_FOLLOWING='TREND_FOLLOWING'
    PULLBACK='PULLBACK'
    BREAKOUT='BREAKOUT'
    SUPPORT_BOUNCE='SUPPORT_BOUNCE'
    OVERSOLD_BOUNCE='OVERSOLD_BOUNCE'
    RANGE_TRADING='RANGE_TRADING'
    MOMENTUM_CONTINUATION='MOMENTUM_CONTINUATION'
    VOLATILITY_SQUEEZE='VOLATILITY_SQUEEZE'
    MA20_REBOUND='MA20_REBOUND'
    TREND_RECOVERY='TREND_RECOVERY'

strategy_pkg=types.ModuleType('app.strategy')
strategy_models=types.ModuleType('app.strategy.models')
strategy_models.StrategyName=_StrategyName
sys.modules.setdefault('app.strategy', strategy_pkg)
sys.modules['app.strategy.models']=strategy_models

from app.backtest.selector import select_strategy


def row(strategy, *, status, passed, total, hist_score, current_score, hist_status='GOOD', risk_warning=False, trades=30):
    missing=max(0,total-passed)
    return {
        'strategy': strategy,
        'label': strategy,
        'historical_fit': {'status': hist_status, 'internal_score': hist_score},
        'historical_metrics': {'trades': trades},
        'current': {
            'status': status,
            'label': '진입 후보' if status=='READY' else '아직 진입 조건 부족',
            'internal_score': current_score,
            'passed': passed,
            'total': total,
            'missing': missing,
            'unmet': [f'missing-{i}' for i in range(missing)],
            'unmet_details': [],
            'risk_warning': risk_warning,
            'warnings': [],
            'conditions_complete': missing == 0,
            'summary': 'summary',
            'decision_reason': 'ENTRY_CANDIDATE' if status=='READY' else 'ENTRY_CONDITIONS_MISSING',
        },
    }


def test_ready_strategy_beats_historically_stronger_wait_strategy_for_current_action():
    support = row('SUPPORT_BOUNCE', status='READY', passed=7, total=7, hist_score=55, current_score=92)
    pullback = row('PULLBACK', status='WATCH', passed=6, total=9, hist_score=100, current_score=80)
    result = select_strategy([support, pullback], as_of_date='20260916', market_regime='TREND_UP')
    assert result['strategy'] == 'SUPPORT_BOUNCE'
    assert result['action'] == 'ENTRY_CANDIDATE'
    assert result['historical_best_strategy'] == 'PULLBACK'
    assert result['selection_rule'] == 'CURRENT_STATE_FIRST'


def test_historical_weak_does_not_turn_ready_into_wait():
    ready = row('SUPPORT_BOUNCE', status='READY', passed=7, total=7, hist_score=10, current_score=95, hist_status='WEAK')
    result = select_strategy([ready], as_of_date='20260916', market_regime='TREND_UP')
    assert result['action'] == 'ENTRY_CANDIDATE'
    assert any('과거 검증 결과는 약합니다' in w for w in result['additional_warnings'])


def test_when_no_ready_strategy_current_closest_wait_is_used():
    a = row('A', status='WATCH', passed=8, total=9, hist_score=20, current_score=88)
    b = row('B', status='WATCH', passed=5, total=9, hist_score=100, current_score=60)
    result = select_strategy([a, b], as_of_date='20260916', market_regime='RANGE')
    assert result['strategy'] == 'A'
    assert result['action'] == 'WAIT'


def test_risk_blocked_ready_like_candidate_is_not_entry_candidate():
    blocked = row('A', status='BLOCKED', passed=7, total=7, hist_score=100, current_score=90, risk_warning=True)
    result = select_strategy([blocked], as_of_date='20260916', market_regime='RANGE')
    assert result['action'] == 'WAIT'
    assert result['decision_reason'] == 'RISK_BLOCKED'
