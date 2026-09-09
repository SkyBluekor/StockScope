from __future__ import annotations

from typing import Any


class AnalysisHubBuilder:
    """Build a short, result-first summary from the independent analysis engines."""

    @staticmethod
    def build(
        *,
        position_mode: str,
        risk_gate: dict[str, Any],
        risk_analysis: dict[str, Any],
        best_regular: Any | None,
        position_action: dict[str, Any],
        relative_strength: dict[str, Any],
        sector_relative_strength: dict[str, Any],
        event_analysis: dict[str, Any],
        pullback_confirmation: dict[str, Any],
        strategy_payloads: list[dict[str, Any]],
        fundamental_analysis: dict[str, Any] | None = None,
        investor_style_analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        holding = position_mode == "HOLDING"
        best_payload = None
        if best_regular is not None:
            best_name = getattr(getattr(best_regular, "strategy", None), "value", None)
            best_payload = next((row for row in strategy_payloads if row.get("strategy") == best_name), None)

        best_score = best_payload.get("score") if best_payload else None
        best_strategy = best_payload.get("strategy") if best_payload else None
        best_suitability = best_payload.get("suitability") if best_payload else None

        fundamental_analysis = fundamental_analysis or {}
        investor_style_analysis = investor_style_analysis or {}
        event_risk_gate = bool(event_analysis.get("risk_gate"))
        negative_events = int(event_analysis.get("negative_count") or 0)
        positive_events = int(event_analysis.get("positive_count") or 0)

        relative_decision = relative_strength.get("decision") or {}
        sector_decision = sector_relative_strength.get("decision") or {}

        signals: list[dict[str, str]] = []

        # Strategy signal
        if risk_gate.get("active"):
            strategy_status = "CAUTION"
            strategy_label = "전략 판단 보류"
            strategy_detail = "Risk Gate가 활성화되어 전략 점수보다 위험 조건을 먼저 봅니다."
        elif best_score is not None and best_score >= 70:
            strategy_status = "POSITIVE"
            strategy_label = "전략 적합도 높음"
            strategy_detail = f"상위 전략 적합도 {best_score}점 · {best_suitability or '높음'}"
        elif best_score is not None and best_score >= 55:
            strategy_status = "NEUTRAL"
            strategy_label = "전략 적합도 보통"
            strategy_detail = f"상위 전략 적합도 {best_score}점"
        else:
            strategy_status = "CAUTION"
            strategy_label = "뚜렷한 전략 부족"
            strategy_detail = "현재 조건에 강하게 맞는 전략이 많지 않습니다."
        signals.append({"key": "strategy", "label": "전략", "status": strategy_status, "value": strategy_label, "detail": strategy_detail})

        # Pullback confirmation signal
        pull_state = str(pullback_confirmation.get("state") or "UNKNOWN")
        pull_auto = pullback_confirmation.get("auto_check") or {}
        pull_entry = pullback_confirmation.get("entry_timing") or {}
        pending_check_labels = [
            str(item.get("label"))
            for item in pull_auto.get("pending_checks", [])
            if item.get("label")
        ]
        pull_progress_label = str(
            pull_auto.get("progress_label")
            or f"{pullback_confirmation.get('passed', 0)}/{pullback_confirmation.get('total_checks', 0)} 조건 확인"
        )
        pullback_relevant = best_strategy in {"pullback", "support_bounce", "ma20_rebound", "trend_recovery"}

        if not pullback_relevant:
            pull_status = "NEUTRAL"
            pull_value = "현재 상위 전략과 직접 연동하지 않음"
            pull_detail = "눌림·지지 자동판정은 참고 데이터로 유지하지만 현재 상위 전략의 행동 게이트로 사용하지 않습니다."
        elif pull_state == "REBOUND_CONFIRMED":
            pull_status = "POSITIVE"
            pull_value = str(pullback_confirmation.get("label") or "반등 확인")
            pull_detail = f"{pull_progress_label} · {str(pullback_confirmation.get('summary') or '')}"
        elif pull_state == "SUPPORT_FAILED":
            pull_status = "NEGATIVE"
            pull_value = str(pullback_confirmation.get("label") or "지지 실패")
            pull_detail = f"{pull_progress_label} · {str(pullback_confirmation.get('summary') or '')}"
        elif pull_state in {"REBOUND_WAITING", "SUPPORT_TESTING", "SUPPORT_APPROACH", "PULLBACK_IN_PROGRESS"}:
            pull_status = "CAUTION"
            pull_value = str(pullback_confirmation.get("label") or "확인 중")
            pull_detail = f"{pull_progress_label} · {str(pullback_confirmation.get('summary') or '')}"
        else:
            pull_status = "NEUTRAL"
            pull_value = str(pullback_confirmation.get("label") or "판단 보류")
            pull_detail = f"{pull_progress_label} · {str(pullback_confirmation.get('summary') or '')}"
        signals.append({
            "key": "pullback",
            "label": "눌림·지지",
            "status": pull_status,
            "value": pull_value,
            "detail": pull_detail,
        })

        # Relative strength
        rs_arch = str(relative_decision.get("archetype") or "UNKNOWN")
        if rs_arch in {"MARKET_LEADER", "OUTPERFORMING"}:
            rs_status = "POSITIVE"
        elif rs_arch in {"MARKET_LAGGARD"}:
            rs_status = "NEGATIVE"
        elif rs_arch in {"SHORT_TERM_RECOVERY", "STRONG_BUT_FADING", "RECOVERY_ATTEMPT"}:
            rs_status = "CAUTION"
        else:
            rs_status = "NEUTRAL"
        signals.append({
            "key": "relative",
            "label": "시장 상대강도",
            "status": rs_status,
            "value": str(relative_decision.get("label") or relative_strength.get("label") or "판단 보류"),
            "detail": str(relative_decision.get("summary") or relative_strength.get("summary") or ""),
        })

        # Sector
        if not sector_relative_strength.get("available"):
            sector_status = "NEUTRAL"
            sector_value = "비교 불가"
        else:
            sector_arch = str(sector_decision.get("archetype") or "UNKNOWN")
            if sector_arch in {"DUAL_LEADER", "INDEPENDENT_LEADER", "WEAK_SECTOR_WINNER"}:
                sector_status = "POSITIVE"
            elif sector_arch in {"SECTOR_LAGGARD", "DOUBLE_LAGGARD"}:
                sector_status = "NEGATIVE"
            else:
                sector_status = "CAUTION"
            sector_value = str(sector_decision.get("label") or sector_relative_strength.get("label") or "판단 보류")
        signals.append({
            "key": "sector",
            "label": "업종 상대강도",
            "status": sector_status,
            "value": sector_value,
            "detail": str(sector_decision.get("summary") or sector_relative_strength.get("message") or ""),
        })

        # Fundamental health
        fundamental_overall = fundamental_analysis.get("overall") or {}
        fundamental_status_code = str(fundamental_overall.get("status") or "UNKNOWN")
        if not fundamental_analysis.get("available"):
            fundamental_status = "NEUTRAL"
            fundamental_value = "데이터 부족"
            fundamental_detail = str(fundamental_overall.get("summary") or "재무 분석을 사용할 수 없습니다.")
        elif fundamental_status_code == "GOOD":
            fundamental_status = "POSITIVE"
            fundamental_value = str(fundamental_overall.get("label") or "양호")
            fundamental_detail = str(fundamental_overall.get("summary") or "재무 체력이 전반적으로 양호합니다.")
        elif fundamental_status_code == "WEAK":
            fundamental_status = "NEGATIVE"
            fundamental_value = str(fundamental_overall.get("label") or "주의")
            fundamental_detail = str(fundamental_overall.get("summary") or "재무 체력에 주의가 필요합니다.")
        else:
            fundamental_status = "CAUTION"
            fundamental_value = str(fundamental_overall.get("label") or "혼합")
            fundamental_detail = str(fundamental_overall.get("summary") or "재무 강점과 약점이 함께 있습니다.")
        signals.append({
            "key": "fundamental",
            "label": "재무 체력",
            "status": fundamental_status,
            "value": fundamental_value,
            "detail": fundamental_detail,
        })

        # Long-term investor style fit. Keep this separate from the short-term action plan.
        top_style = investor_style_analysis.get("top_style") or {}
        if not investor_style_analysis.get("available") or not top_style:
            style_status = "NEUTRAL"
            style_value = "판단 보류"
            style_detail = str(investor_style_analysis.get("message") or "투자 스타일 적합도 데이터가 부족합니다.")
        else:
            style_fit = str(top_style.get("fit") or "UNKNOWN")
            if style_fit in {"VERY_HIGH", "HIGH"}:
                style_status = "POSITIVE"
            elif style_fit == "MEDIUM":
                style_status = "CAUTION"
            else:
                style_status = "NEUTRAL"
            style_value = f"{top_style.get('label') or '투자 스타일'} · {top_style.get('fit_label') or '판단 보류'}"
            style_detail = str(top_style.get("action_summary") or top_style.get("summary") or investor_style_analysis.get("message") or "")
        signals.append({
            "key": "investor_style",
            "label": "장기 투자 스타일",
            "status": style_status,
            "value": style_value,
            "detail": style_detail,
        })

        # Events
        if event_risk_gate:
            event_status = "NEGATIVE"
            event_value = "중요 부정 공시 우선"
            event_detail = "최근 중요 공시가 Risk Gate에 반영됐습니다."
        elif positive_events > negative_events and positive_events > 0:
            event_status = "POSITIVE"
            event_value = "긍정 이벤트 우세"
            event_detail = str(event_analysis.get("message") or "")
        elif negative_events > 0:
            event_status = "CAUTION"
            event_value = "부정 이벤트 있음"
            event_detail = str(event_analysis.get("message") or "")
        else:
            event_status = "NEUTRAL"
            event_value = "큰 악재 신호 없음"
            event_detail = str(event_analysis.get("message") or "")
        signals.append({"key": "event", "label": "공시", "status": event_status, "value": event_value, "detail": event_detail})

        # Risk structure
        risk_status_value = str(risk_analysis.get("status") or "UNAVAILABLE")
        if risk_gate.get("active") or risk_status_value == "HOLD":
            risk_status = "NEGATIVE"
            risk_value = "위험 확인 우선"
        elif risk_status_value == "CAUTION":
            risk_status = "CAUTION"
            risk_value = "주의"
        elif risk_status_value == "READY":
            risk_status = "POSITIVE"
            risk_value = "구조 양호"
        else:
            risk_status = "NEUTRAL"
            risk_value = "계산 부족"
        signals.append({
            "key": "risk",
            "label": "리스크",
            "status": risk_status,
            "value": risk_value,
            "detail": str(risk_analysis.get("summary") or ""),
        })

        positives = sum(item["status"] == "POSITIVE" for item in signals)
        negatives = sum(item["status"] == "NEGATIVE" for item in signals)
        cautions = sum(item["status"] == "CAUTION" for item in signals)

        reasons: list[str] = []
        change_conditions: list[str] = []

        if holding and position_action.get("available"):
            primary_action = str(position_action.get("primary_label") or "보유 관찰")
            action_summary = str(position_action.get("summary") or "")
            reasons.extend(position_action.get("why") or [])
            for trigger in position_action.get("triggers") or []:
                condition = trigger.get("condition")
                effect = trigger.get("effect")
                if condition and effect:
                    change_conditions.append(f"{condition} → {effect}")
        else:
            if risk_gate.get("active"):
                primary_action = "신규 진입 보류"
                action_summary = str(risk_gate.get("message") or "현재는 위험 조건 확인이 우선입니다.")
            elif pullback_relevant and pull_state == "REBOUND_CONFIRMED" and best_score is not None and best_score >= 55:
                primary_action = "눌림목 후보 우선 검토"
                action_summary = f"{pull_progress_label}. 앱이 지지 후 반등 조건을 확인했습니다. Risk Gate와 손익 구조를 함께 비교할 수 있는 단계입니다."
            elif pullback_relevant and pull_state == "REBOUND_WAITING":
                primary_action = "반등 신호 대기"
                missing = " · ".join(pending_check_labels[:3]) or "남은 회복 조건"
                action_summary = f"지지 유지까지는 확인됐습니다. {pull_progress_label}. 아직 {missing} 확인이 남아 앱이 다음 데이터에서 자동 재판정합니다."
            elif pullback_relevant and pull_state == "SUPPORT_TESTING":
                primary_action = "신규 진입 대기"
                missing = " · ".join(pending_check_labels[:3]) or "지지 방어 조건"
                action_summary = f"지지구간에는 도착했지만 아직 {missing} 확인이 부족합니다. {pull_progress_label}."
            elif pullback_relevant and pull_state == "SUPPORT_APPROACH":
                primary_action = "지지구간 도달 대기"
                action_summary = f"주가가 지지 후보로 접근 중입니다. {pull_progress_label}. 실제 지지 테스트 구간에 들어오면 앱이 방어 여부를 자동 판정합니다."
            elif pullback_relevant and pull_state == "PULLBACK_IN_PROGRESS":
                primary_action = "눌림 조건 형성 대기"
                action_summary = f"조정은 진행 중이지만 아직 핵심 지지 확인 단계는 아닙니다. {pull_progress_label}."
            elif best_score is not None and best_score >= 70 and negatives == 0:
                primary_action = "우선 관찰 후보"
                action_summary = "전략 적합도와 상대강도 중 긍정 신호가 우세합니다. 다만 진입 위치와 Risk Engine 기준을 함께 봅니다."
            else:
                primary_action = "조건 확인 대기"
                action_summary = "현재는 한 가지 방향으로 강하게 결론 내리기보다 전략·위험 조건의 추가 확인이 낫습니다."

            if pullback_relevant:
                reasons.append(str(pullback_confirmation.get("summary") or ""))
            reasons.append(str(relative_decision.get("summary") or ""))
            if sector_relative_strength.get("available"):
                reasons.append(str(sector_decision.get("summary") or ""))
            if event_analysis.get("message"):
                reasons.append(str(event_analysis.get("message")))

            if pullback_relevant:
                change_conditions.extend(pullback_confirmation.get("waiting_for") or [])
            change_conditions.extend(relative_decision.get("watch_points") or [])
            if sector_relative_strength.get("available"):
                change_conditions.extend(sector_decision.get("watch_points") or [])

        if fundamental_analysis.get("available"):
            fundamental_reason = str(fundamental_overall.get("summary") or "")
            if fundamental_reason:
                reasons.append(f"재무: {fundamental_reason}")
            for point in (fundamental_analysis.get("watch_points") or [])[:2]:
                change_conditions.append(str(point))

        reasons = [item for item in reasons if item][:4]
        change_conditions = list(dict.fromkeys(item for item in change_conditions if item))[:5]

        if risk_gate.get("active") or negatives >= 2:
            verdict_code = "RISK_FIRST"
            verdict_label = "위험 확인 우선"
            headline = "현재는 긍정 신호보다 위험 조건을 먼저 확인해야 합니다."
        elif positives >= 3 and negatives == 0:
            verdict_code = "POSITIVE_CAUTION" if cautions else "POSITIVE"
            verdict_label = "긍정 우세 · 조건부"
            headline = "여러 분석축에서 긍정 신호가 우세하지만 진입 위치는 따로 봐야 합니다."
        elif positives >= 2 and negatives <= 1:
            verdict_code = "MIXED_POSITIVE"
            verdict_label = "긍정 우세 · 주의 병존"
            headline = "좋은 신호가 더 많지만 일부 약점 때문에 한 번 더 확인할 구간입니다."
        elif negatives > positives:
            verdict_code = "CAUTION"
            verdict_label = "주의 우세"
            headline = "현재는 공격적인 판단보다 약한 부분이 회복되는지 보는 편이 낫습니다."
        else:
            verdict_code = "MIXED"
            verdict_label = "혼합 · 확인 대기"
            headline = "분석축들이 엇갈려 한 방향으로 단정하기 어렵습니다."

        if fundamental_analysis.get("available") and fundamental_status_code == "WEAK" and positives >= 2 and not risk_gate.get("active"):
            verdict_code = "MIXED_POSITIVE"
            verdict_label = "가격 신호 긍정 · 재무 주의"
            headline = "가격 흐름은 강하지만 재무 체력이 이를 충분히 뒷받침하지 못합니다."
        elif fundamental_analysis.get("available") and fundamental_status_code == "GOOD" and positives >= 3 and negatives == 0:
            verdict_label = "긍정 우세 · 재무 뒷받침"
            headline = "가격 흐름과 재무 체력이 함께 긍정적인 편입니다."

        risk_level = "높음" if risk_gate.get("active") or negatives >= 2 else "보통" if cautions or negatives else "낮음"

        # Translate analytical signals into explicit decision effects.
        for signal in signals:
            key = signal["key"]
            status = signal["status"]
            if key == "strategy":
                if best_score is not None and best_score >= 70 and pullback_relevant and pull_state != "REBOUND_CONFIRMED":
                    hint = "전략 형태는 잘 맞지만 현재 진입 신호가 완성됐다는 뜻은 아닙니다."
                elif status == "POSITIVE":
                    hint = "현재 후보 전략의 우선순위를 높이는 요소입니다."
                else:
                    hint = "전략 점수만으로 현재 행동을 확정하지 않습니다."
            elif key == "pullback":
                if pull_state == "REBOUND_CONFIRMED":
                    hint = "지지 후 반등 조건이 확인돼 다음 단계 검토가 가능합니다."
                elif pull_state == "SUPPORT_FAILED":
                    hint = "눌림 전략의 전제가 약해져 신규 판단을 보류하는 핵심 이유입니다."
                elif pull_state in {"REBOUND_WAITING", "SUPPORT_TESTING", "SUPPORT_APPROACH", "PULLBACK_IN_PROGRESS"}:
                    hint = "현재 행동을 '대기'로 만드는 핵심 조건입니다."
                else:
                    hint = "현재 우선 전략이 눌림 계열이 아니면 보조 정보로 사용합니다."
            elif key == "relative":
                hint = (
                    "시장보다 약해 신규 후보 우선순위를 낮추는 요소입니다."
                    if status == "NEGATIVE"
                    else "시장보다 강해 후보 우선순위를 높이는 요소입니다."
                    if status == "POSITIVE"
                    else "시장 대비 힘이 명확하지 않아 보조 판단으로 사용합니다."
                )
            elif key == "sector":
                hint = (
                    "같은 업종 안에서도 약해 후보 우선순위를 낮추는 요소입니다."
                    if status == "NEGATIVE"
                    else "업종 안에서도 상대적으로 강한 점은 긍정 근거입니다."
                    if status == "POSITIVE"
                    else "업종 비교는 현재 결론을 강하게 바꾸는 신호가 아닙니다."
                )
            elif key == "fundamental":
                hint = (
                    "재무 체력이 약해 중장기 관점의 확신을 낮추는 요소입니다."
                    if status == "NEGATIVE"
                    else "재무 체력이 가격 신호를 보조하는 근거입니다."
                    if status == "POSITIVE"
                    else "재무 강점과 약점이 섞여 보조 판단으로 사용합니다."
                )
            elif key == "investor_style":
                hint = (
                    "장기 투자철학 관점의 기업 적합도가 높은 편입니다. 현재 단기 진입 단계와는 별개입니다."
                    if status == "POSITIVE"
                    else "어떤 투자철학과 맞는지 비교하는 보조 정보이며 현재 진입 신호는 아닙니다."
                )
            elif key == "event":
                hint = (
                    "중요 부정 공시가 있어 다른 긍정 신호보다 우선 확인합니다."
                    if status == "NEGATIVE"
                    else "긍정 공시는 보조 근거이며 가격·위험 조건을 대신하지 않습니다."
                    if status == "POSITIVE"
                    else "공시는 현재 행동을 크게 바꾸는 핵심 신호가 아닙니다."
                )
            else:  # risk
                hint = (
                    "현재 행동을 보류시키는 최우선 위험 조건입니다."
                    if status == "NEGATIVE"
                    else "구조가 아직 무효화되지 않았다는 뜻이지 진입 신호는 아닙니다."
                    if status == "POSITIVE"
                    else "손익 구조와 무효화 기준을 함께 봅니다."
                )
            signal["action_hint"] = hint

        # Rank only the most decision-relevant factors for the first screen.
        base_priority = {
            "risk": 100,
            "pullback": 98 if pullback_relevant else 62,
            "event": 88,
            "relative": 84,
            "sector": 82,
            "fundamental": 76,
            "strategy": 72,
            "investor_style": 64,
        }
        status_priority = {"NEGATIVE": 24, "CAUTION": 15, "POSITIVE": 8, "NEUTRAL": 0}
        ranked_signals = sorted(
            signals,
            key=lambda item: base_priority.get(item["key"], 50) + status_priority.get(item["status"], 0),
            reverse=True,
        )
        priority_signals = ranked_signals[:3]
        other_signals = ranked_signals[3:]

        risk_plan = risk_analysis.get("selected_plan") or {}
        anchor = pullback_confirmation.get("anchor") or {}

        entry_levels = dict(pull_entry.get("levels") or {})
        entry_levels["invalidation"] = (
            float(risk_plan["invalidation_price"])
            if risk_plan.get("invalidation_price") is not None
            else None
        )
        top_style = investor_style_analysis.get("top_style") or {}
        entry_timing = {
            "version": "0.18.2",
            "relevant": bool(pullback_relevant),
            "status": str(pull_entry.get("status") or "WAIT"),
            "state": pull_state,
            "label": str(pull_entry.get("label") or pullback_confirmation.get("label") or "판단 보류"),
            "headline": str(pull_entry.get("headline") or pullback_confirmation.get("headline") or ""),
            "summary": str(pull_entry.get("summary") or pullback_confirmation.get("summary") or ""),
            "basis": str(pull_entry.get("basis") or pullback_confirmation.get("basis") or "CONFIRMED_EOD"),
            "basis_label": str(pull_entry.get("basis_label") or pullback_confirmation.get("basis_label") or "KRX 확정 EOD"),
            "progress": pull_entry.get("progress") or {
                "passed": int(pull_auto.get("passed") or 0),
                "failed": int(pull_auto.get("failed") or 0),
                "pending": int(pull_auto.get("pending") or 0),
                "total": int(pull_auto.get("total") or 0),
                "percent": int(pull_auto.get("progress_pct") or 0),
                "label": pull_progress_label,
            },
            "confirmed_checks": (pull_entry.get("confirmed_checks") or pull_auto.get("passed_checks") or [])[:7],
            "failed_checks": (pull_entry.get("failed_checks") or pull_auto.get("failed_checks") or [])[:4],
            "pending_checks": (pull_entry.get("pending_checks") or pull_auto.get("pending_checks") or [])[:7],
            "most_missing": (pull_entry.get("most_missing") or pending_check_labels)[:3],
            "action": pull_entry.get("action") or {
                "perspective": "보유 관리" if holding else "신규 진입",
                "primary": primary_action,
                "next": "다음 데이터에서 자동 재평가",
                "avoid": "조건 미완료 상태의 성급한 판단",
                "recheck_note": str(pull_auto.get("next_data_note") or "다음 분석에서 자동 재판정합니다."),
            },
            "levels": entry_levels,
            "rules": pull_entry.get("rules") or {},
            "style_context": {
                "label": str(top_style.get("label") or ""),
                "score": top_style.get("score"),
                "fit_label": str(top_style.get("fit_label") or ""),
                "summary": (
                    f"기업 자체는 {top_style.get('label')} 기준 {top_style.get('fit_label')}이지만 단기 진입 타이밍은 별도로 판정합니다."
                    if top_style.get("label")
                    else "기업 스타일 적합도와 단기 진입 타이밍은 별도 축으로 판정합니다."
                ),
            },
            "policy": str(pull_entry.get("policy") or "조건 확인 개수는 상승확률이 아닙니다."),
        }

        price_levels: list[dict[str, Any]] = []
        if anchor.get("price") is not None:
            price_levels.append({
                "key": "support",
                "label": str(anchor.get("name") or "주요 지지"),
                "price": float(anchor["price"]),
                "meaning": "이 구간이 유지되는지 앱이 자동 확인합니다.",
            })
        if risk_plan.get("invalidation_price") is not None:
            price_levels.append({
                "key": "invalidation",
                "label": "전략 무효화 기준",
                "price": float(risk_plan["invalidation_price"]),
                "meaning": "하향 이탈하면 현재 전략의 전제를 다시 평가합니다.",
            })

        do_now: list[str] = []
        avoid_now: list[str] = []
        decision_scenarios: list[dict[str, str]] = []

        if holding and position_action.get("available"):
            hold_info = position_action.get("hold") or {}
            add_info = position_action.get("add_position") or {}
            reduce_info = position_action.get("reduce_position") or {}
            if hold_info.get("label"):
                do_now.append(f"{hold_info['label']}: {hold_info.get('reason') or '현재 보유 구조를 앱 기준으로 관찰합니다.'}")
            if add_info.get("label"):
                if str(add_info.get("decision") or "").upper() in {"WAIT", "HOLD", "NO"}:
                    avoid_now.append(f"{add_info['label']}: {add_info.get('reason') or '추가 조건이 확인되기 전까지 비중 확대를 보류합니다.'}")
                else:
                    do_now.append(f"{add_info['label']}: {add_info.get('reason') or '추가 조건을 확인합니다.'}")
            if reduce_info.get("label") and str(reduce_info.get("decision") or "").upper() not in {"NONE", "NO", "HOLD"}:
                do_now.append(f"{reduce_info['label']}: {reduce_info.get('reason') or '리스크 축소 조건을 확인합니다.'}")
            for trigger in (position_action.get("triggers") or [])[:3]:
                if trigger.get("condition") and trigger.get("effect"):
                    decision_scenarios.append({
                        "condition": str(trigger["condition"]),
                        "effect": str(trigger["effect"]),
                        "tone": "CAUTION",
                    })
        else:
            if risk_gate.get("active"):
                do_now.append("Risk Gate가 켜진 원인을 먼저 확인하고 신규 후보 판단은 보류합니다.")
                avoid_now.append("전략 점수가 높다는 이유만으로 현재 진입을 확정하지 않습니다.")
                decision_scenarios.append({
                    "condition": "Risk Gate 원인이 해소되고 위험 구조가 다시 계산됨",
                    "effect": "신규 후보 평가를 다시 시작",
                    "tone": "POSITIVE",
                })
            elif pullback_relevant and pull_state in {"REBOUND_WAITING", "SUPPORT_TESTING", "SUPPORT_APPROACH", "PULLBACK_IN_PROGRESS"}:
                do_now.append("앱이 지지 유지와 반등 조건을 자동 확인하도록 현재 후보를 대기 상태로 둡니다.")
                if pending_check_labels:
                    do_now.append(f"현재 핵심 대기 조건: {' · '.join(pending_check_labels[:3])}")
                avoid_now.append("반등 확인 전에는 높은 전략 점수를 '진입 신호'로 해석하지 않습니다.")
                support_prefix = (
                    f"{float(anchor['price']):,.0f}원 지지 유지 + "
                    if anchor.get("price") is not None
                    else "지지 유지 + "
                )
                decision_scenarios.append({
                    "condition": support_prefix + "가격 반등 + RSI/거래량 회복 조건 충족",
                    "effect": "반등 확인 단계로 올라가 신규 후보 검토 가능",
                    "tone": "POSITIVE",
                })
            elif pullback_relevant and pull_state == "SUPPORT_FAILED":
                do_now.append("눌림 전략의 지지 실패 원인을 확인하고 다른 전략 후보와 다시 비교합니다.")
                avoid_now.append("깨진 지지선을 근거로 기존 눌림 전략을 그대로 유지하지 않습니다.")
            elif pullback_relevant and pull_state == "REBOUND_CONFIRMED":
                do_now.append("반등 확인은 완료됐으므로 Risk Engine의 무효화 기준과 손익 구조를 함께 비교합니다.")
                avoid_now.append("반등 확인 하나만으로 실제 진입을 자동 확정하지 않습니다.")
            elif best_score is not None and best_score >= 70:
                do_now.append("상위 전략 후보는 유지하되 상대강도·Risk Engine과 함께 최종 후보 우선순위를 비교합니다.")
                avoid_now.append("전략 적합도 점수를 상승확률로 해석하지 않습니다.")
            else:
                do_now.append("현재는 강한 단일 신호가 부족하므로 앱의 다음 자동 재평가를 기다립니다.")
                avoid_now.append("조건이 불완전한 상태에서 억지로 하나의 전략을 선택하지 않습니다.")

            if risk_plan.get("invalidation_price") is not None:
                decision_scenarios.append({
                    "condition": f"{float(risk_plan['invalidation_price']):,.0f}원 하향 이탈",
                    "effect": "현재 전략 무효화·리스크 재평가",
                    "tone": "NEGATIVE",
                })
            if rs_status == "NEGATIVE":
                decision_scenarios.append({
                    "condition": "20일 시장 상대강도가 0%p 이상으로 회복",
                    "effect": "시장 소외 감점이 줄어 후보 우선순위 재평가",
                    "tone": "POSITIVE",
                })
            elif sector_status == "NEGATIVE":
                decision_scenarios.append({
                    "condition": "업종 대비 상대강도가 회복",
                    "effect": "동종 종목 대비 열위 감점이 줄어 후보 우선순위 재평가",
                    "tone": "POSITIVE",
                })

        do_now = list(dict.fromkeys(item for item in do_now if item))[:3]
        avoid_now = list(dict.fromkeys(item for item in avoid_now if item))[:3]
        decision_scenarios = decision_scenarios[:4]

        blockers: list[str] = []
        if risk_gate.get("active"):
            blockers.append("Risk Gate 활성")
        if pullback_relevant and pull_state != "REBOUND_CONFIRMED":
            if pull_state == "SUPPORT_FAILED":
                blockers.append("지지 실패")
            elif pull_state not in {"NOT_PULLBACK", "UNKNOWN"}:
                blockers.append("반등 확인 미완료")
        if rs_status == "NEGATIVE":
            blockers.append("시장 상대강도 약세")
        if sector_status == "NEGATIVE":
            blockers.append("업종 상대강도 약세")
        if fundamental_status == "NEGATIVE":
            blockers.append("재무 체력 주의")

        conflict = {
            "show": bool(best_score is not None and best_score >= 80 and blockers),
            "headline": (
                f"전략 적합도 {best_score}점인데 왜 '{primary_action}'인가?"
                if best_score is not None
                else ""
            ),
            "summary": (
                "전략 점수는 현재 가격 구조가 해당 전략의 형태와 얼마나 맞는지를 뜻하며 "
                "현재 진입 신호가 아닙니다. 현재는 "
                + " · ".join(blockers[:3])
                + " 때문에 행동 단계가 제한됩니다."
                if blockers
                else ""
            ),
            "blockers": blockers[:4],
        }

        if holding:
            action_headline = f"현재 보유 대응은 '{primary_action}'입니다."
        elif risk_gate.get("active"):
            action_headline = "지금은 신규 진입보다 위험 조건 해소 확인이 먼저입니다."
        elif pullback_relevant and pull_state in {"REBOUND_WAITING", "SUPPORT_TESTING", "SUPPORT_APPROACH", "PULLBACK_IN_PROGRESS"}:
            action_headline = "지금은 반등 확인 전까지 신규 진입을 확정하지 않는 단계입니다."
        elif pullback_relevant and pull_state == "SUPPORT_FAILED":
            action_headline = "현재 눌림 전략은 지지 실패로 재평가가 필요합니다."
        elif pullback_relevant and pull_state == "REBOUND_CONFIRMED":
            action_headline = "반등 조건은 확인됐고 이제 위험·손익 구조를 비교할 단계입니다."
        else:
            action_headline = f"현재 대응은 '{primary_action}'입니다."

        action_plan = {
            "status": (
                "HOLDING"
                if holding
                else "RISK_REVIEW"
                if risk_gate.get("active")
                else "READY"
                if pull_state == "REBOUND_CONFIRMED"
                else "WAIT"
                if any(token in primary_action for token in ("대기", "보류"))
                else "REVIEW"
            ),
            "label": primary_action,
            "headline": action_headline,
            "summary": action_summary,
            "do_now": do_now,
            "avoid_now": avoid_now,
            "decision_scenarios": decision_scenarios,
            "price_levels": price_levels,
            "conflict": conflict,
        }

        auto_check_status = {
            "state": pull_state,
            "label": str(pullback_confirmation.get("label") or "판단 보류"),
            "headline": str(pullback_confirmation.get("headline") or ""),
            "basis": str(pullback_confirmation.get("basis") or "CONFIRMED_EOD"),
            "basis_label": str(pullback_confirmation.get("basis_label") or "KRX 확정 EOD"),
            "confirmed": bool(pullback_confirmation.get("confirmed")),
            "progress": {
                "passed": int(pull_auto.get("passed") or 0),
                "failed": int(pull_auto.get("failed") or 0),
                "pending": int(pull_auto.get("pending") or 0),
                "total": int(pull_auto.get("total") or pullback_confirmation.get("total_checks") or 0),
                "percent": int(pull_auto.get("progress_pct") or 0),
                "label": pull_progress_label,
            },
            "pending": (pull_auto.get("pending_checks") or [])[:4],
            "failed": (pull_auto.get("failed_checks") or [])[:3],
            "input_hints": pull_auto.get("input_hints") or [],
            "next_data_note": str(pull_auto.get("next_data_note") or "다음 분석에서 자동 재판정합니다."),
            "policy": str(pull_auto.get("policy") or "조건 확인 개수는 상승확률이 아닙니다."),
        }

        return {
            "version": "0.18.2",
            "verdict_code": verdict_code,
            "verdict_label": verdict_label,
            "headline": action_headline,
            "summary": action_summary,
            "primary_action": primary_action,
            "action_plan": action_plan,
            "perspective": "보유 관리" if holding else "신규 진입",
            "risk_level": risk_level,
            "auto_check_status": auto_check_status,
            "entry_timing": entry_timing,
            "signals": signals,
            "priority_signals": priority_signals,
            "other_signals": other_signals,
            "top_strategy": {
                "strategy": best_strategy,
                "score": best_score,
                "suitability": best_suitability,
            },
            "key_reasons": reasons,
            "change_conditions": change_conditions,
            "navigation": [
                {"key": "summary", "label": "종합", "description": "현재 결론과 대응"},
                {"key": "strategy", "label": "전략", "description": "눌림 확인·전략 비교"},
                {"key": "fundamental", "label": "재무", "description": "기업 체력·실적·현금흐름"},
                {"key": "investor_style", "label": "투자스타일", "description": "Buffett·Graham·Lynch·CAN SLIM"},
                {"key": "risk", "label": "위험", "description": "Risk Gate·손익 구조"},
                {"key": "relative", "label": "상대강도", "description": "시장·업종 비교"},
                {"key": "event", "label": "공시", "description": "OpenDART 영향"},
                {"key": "indicators", "label": "지표", "description": "기술지표·용어"},
            ],
            "policy": "종합 요약은 여러 분석 엔진의 결과를 압축한 의사결정 보조이며 실제 주문 지시가 아닙니다.",
        }
