import { useEffect, useId, useRef, useState } from "react";
import type { ReactNode } from "react";

export type TermKey =
  | "ma"
  | "rsi"
  | "atr"
  | "volume_ratio"
  | "support"
  | "resistance"
  | "breakout"
  | "pullback"
  | "momentum"
  | "trend"
  | "overbought"
  | "oversold"
  | "invalidation"
  | "stop"
  | "target"
  | "risk_reward"
  | "risk_gate"
  | "relative_strength"
  | "sector_relative_strength"
  | "excess_return"
  | "eod"
  | "volatility"
  | "higher_low"
  | "higher_high"
  | "strategy_score"
  | "fundamental_health"
  | "revenue"
  | "operating_profit"
  | "net_income"
  | "operating_margin"
  | "roe"
  | "roa"
  | "eps"
  | "bps"
  | "per"
  | "pbr"
  | "debt_ratio"
  | "current_ratio"
  | "operating_cash_flow"
  | "free_cash_flow"
  | "market_cap"
  | "value_investing"
  | "growth_investing"
  | "margin_of_safety"
  | "economic_moat"
  | "peg"
  | "earnings_quality"
  | "can_slim"
  | "investment_style_fit"
  | "event_impact";

type TermDefinition = {
  title: string;
  short: string;
  detail: string;
  read: string;
  caution?: string;
};

export const TERM_DEFINITIONS: Record<TermKey, TermDefinition> = {
  ma: {
    title: "이동평균선(MA)",
    short: "최근 일정 기간의 주가 평균을 선으로 이어 만든 기준선입니다.",
    detail: "20일선은 최근 20거래일 종가의 평균입니다. 현재 주가가 평균보다 위인지 아래인지, 평균선 자체가 올라가는지 내려가는지를 보면서 단기 추세를 확인합니다.",
    read: "주가가 상승하는 20일선 위에 있으면 단기 상승 흐름이 유지되는 쪽으로 해석할 수 있습니다.",
    caution: "20일선을 한 번 이탈했다고 바로 하락 추세가 확정되는 것은 아닙니다.",
  },
  rsi: {
    title: "RSI",
    short: "최근 상승과 하락의 힘을 0~100으로 나타낸 지표입니다.",
    detail: "RSI14는 최근 14거래일의 상승폭과 하락폭을 비교합니다. 숫자가 높을수록 최근 매수 힘이 강했고, 낮을수록 최근 매도 힘이 강했다는 뜻입니다.",
    read: "보통 70 이상은 과열 가능성, 30 이하는 과매도 가능성, 40~60 부근은 중립 구간으로 참고합니다.",
    caution: "RSI 70 이상이 곧바로 하락한다는 뜻은 아닙니다. 강한 상승 종목은 높은 RSI를 오래 유지할 수 있습니다.",
  },
  atr: {
    title: "ATR",
    short: "최근 주가가 하루에 얼마나 크게 움직였는지를 나타내는 평균 변동폭입니다.",
    detail: "ATR은 단순 고가-저가뿐 아니라 전일 종가와의 갭까지 고려해 실제 체감 변동폭을 계산합니다.",
    read: "ATR%가 높을수록 하루 변동이 큰 종목입니다. 손절·목표 가격을 너무 촘촘하게 잡으면 평범한 변동에도 기준이 깨질 수 있습니다.",
    caution: "ATR은 방향을 알려주는 지표가 아닙니다. 많이 움직이는지 적게 움직이는지만 보여줍니다.",
  },
  volume_ratio: {
    title: "거래량 비율",
    short: "현재 거래량이 최근 평균보다 얼마나 많은지 비교한 값입니다.",
    detail: "1.0배는 최근 20일 평균 수준, 2.0배는 평균의 약 두 배가 거래됐다는 뜻입니다.",
    read: "돌파나 급등이 큰 거래량과 함께 나오면 시장 참여가 강하다는 근거가 될 수 있습니다.",
    caution: "거래량이 많다고 상승이 보장되는 것은 아닙니다. 대량 매도 때문에 거래량이 커질 수도 있습니다.",
  },
  support: {
    title: "지지선 / 지지 가격",
    short: "주가가 내려왔을 때 매수세가 들어오며 버틸 가능성이 있는 가격대입니다.",
    detail: "최근 저점, 반복해서 반등한 가격, 이동평균선 등을 이용해 지지 후보를 찾습니다.",
    read: "현재가가 지지선 위에서 버티면 기존 상승 논리가 유지되는 근거가 될 수 있습니다.",
    caution: "지지선은 바닥을 보장하는 가격이 아닙니다. 강하게 깨지면 오히려 약세 신호가 될 수 있습니다.",
  },
  resistance: {
    title: "저항선 / 저항 가격",
    short: "주가가 올라갈 때 매도세가 나오기 쉬운 가격대입니다.",
    detail: "최근 고점이나 여러 번 상승이 막힌 가격대를 저항 후보로 봅니다.",
    read: "저항을 거래량과 함께 넘으면 돌파 전략에서는 긍정적으로 평가할 수 있습니다.",
    caution: "저항을 잠깐 넘었다가 다시 내려오는 가짜 돌파도 있습니다.",
  },
  breakout: {
    title: "돌파",
    short: "주가가 이전 고점이나 저항 가격을 위로 넘어서는 움직임입니다.",
    detail: "단순히 가격만 넘는 것보다 거래량 증가, 시장 대비 강도, 종가 유지 여부를 함께 보는 편이 좋습니다.",
    read: "저항을 넘어선 뒤 그 가격 위에서 버티면 돌파의 신뢰도가 높아질 수 있습니다.",
    caution: "급등한 뒤 뒤늦게 따라가는 추격매수와 돌파 전략은 같은 말이 아닙니다.",
  },
  pullback: {
    title: "눌림목",
    short: "상승하던 주가가 잠깐 조정받아 지지 구간으로 내려오는 구간입니다.",
    detail: "상승 추세는 유지되지만 단기 과열이 식으면서 20일선이나 이전 돌파 가격 근처로 돌아오는 상황을 주로 봅니다.",
    read: "조정 후 지지선이 유지되고 다시 상승 힘이 생기는지를 확인합니다.",
    caution: "계속 떨어지는 종목을 단순히 '눌림목'이라고 부르면 안 됩니다. 추세 유지 여부가 중요합니다.",
  },
  momentum: {
    title: "모멘텀",
    short: "주가가 한 방향으로 움직이는 힘과 속도입니다.",
    detail: "최근 수익률, 거래량, 신고가 접근, 시장 대비 상대강도 등을 함께 사용해 상승 힘이 지속되는지를 봅니다.",
    read: "모멘텀이 강하면 추세가 이어질 가능성을 검토할 수 있지만 과열 여부도 같이 봐야 합니다.",
  },
  trend: {
    title: "추세",
    short: "주가가 일정 기간 동안 주로 움직이는 방향입니다.",
    detail: "고점과 저점이 계속 높아지면 상승 추세, 반대로 낮아지면 하락 추세로 해석합니다.",
    read: "추세 전략은 정확한 바닥을 맞히기보다 이미 확인된 방향을 따라가는 데 초점을 둡니다.",
  },
  overbought: {
    title: "과매수 / 과열",
    short: "최근 매수세가 매우 강해 단기적으로 가격이 빠르게 오른 상태를 뜻합니다.",
    detail: "RSI 70 이상 같은 조건을 참고하지만, 과열이라는 말 자체가 바로 매도 신호는 아닙니다.",
    read: "추격 부담과 단기 변동성 확대 가능성을 함께 봅니다.",
  },
  oversold: {
    title: "과매도",
    short: "최근 매도세가 강해 주가가 빠르게 내려온 상태를 뜻합니다.",
    detail: "RSI 30 이하 같은 조건을 참고합니다.",
    read: "반등 가능성을 살펴볼 수 있는 구간이지만 하락 추세가 끝났다는 뜻은 아닙니다.",
  },
  invalidation: {
    title: "전략 무효화 기준",
    short: "이 가격이 깨지면 '내가 이 전략을 선택한 이유'가 약해졌다고 보는 기준입니다.",
    detail: "예를 들어 지지선 반등 전략이라면 핵심 지지 가격을 강하게 이탈했을 때 기존 전략 논리를 다시 평가합니다.",
    read: "손익률보다 중요한 것은 처음 세운 전략의 전제가 아직 살아 있는지입니다.",
    caution: "무효화 가격은 실제 자동 주문가격이 아니라 분석 참고 기준입니다.",
  },
  stop: {
    title: "손절 참고구간",
    short: "손실이 더 커지기 전에 위험을 다시 평가할 가격 구간입니다.",
    detail: "지지선, ATR, 최근 저점, 전략 무효화 기준을 이용해 참고 구간을 계산합니다.",
    read: "현재가가 이 구간에 가까워질수록 기존 전략을 계속 유지할 근거가 남아 있는지 다시 봅니다.",
    caution: "StockScope는 실제 손절 주문을 실행하지 않습니다.",
  },
  target: {
    title: "목표가 참고",
    short: "현재 전략이 유지될 때 다음 저항이나 손익비를 기준으로 보는 참고 가격입니다.",
    detail: "목표가는 미래 가격을 보장하는 예측값이 아니라 손익 구조를 비교하기 위한 기준입니다.",
    read: "목표가에 가까워질수록 남은 상승 여지와 현재 위험을 다시 비교하는 참고점으로 사용합니다.",
  },
  risk_reward: {
    title: "R:R (Risk : Reward)",
    short: "감수할 손실과 기대하는 보상의 비율입니다.",
    detail: "예를 들어 1:2는 1만큼의 위험을 감수할 때 목표 보상이 2만큼이라는 뜻입니다.",
    read: "같은 전략이라도 손절은 멀고 목표는 가까우면 손익 구조가 불리할 수 있습니다.",
    caution: "R:R이 높다고 목표 달성 확률까지 높다는 뜻은 아닙니다.",
  },
  risk_gate: {
    title: "Risk Gate",
    short: "전략 점수보다 위험 조건을 먼저 적용해 신규 진입 판단을 보류하는 안전장치입니다.",
    detail: "급격한 가격변동, 중요한 부정 공시, 데이터 신선도 문제 등 기존 전략을 그대로 믿기 어려운 상황에서 작동합니다.",
    read: "Risk Gate가 켜지면 높은 전략 점수가 있어도 신규 진입 판단보다 위험 확인을 우선합니다.",
  },
  relative_strength: {
    title: "상대강도",
    short: "이 종목이 시장보다 더 강하게 움직였는지를 비교한 값입니다.",
    detail: "종목 수익률에서 KOSPI/KOSDAQ 수익률을 비교해 시장이 좋았기 때문에 오른 것인지, 종목 자체가 더 강했는지를 구분합니다.",
    read: "시장보다 꾸준히 강한 종목은 추세·모멘텀 전략의 우선순위를 높이는 근거가 될 수 있습니다.",
  },
  sector_relative_strength: {
    title: "업종 상대강도",
    short: "같은 업종 전체와 비교해서 이 종목이 더 강한지 보는 값입니다.",
    detail: "시장보다 올랐더라도 같은 업종이 더 많이 올랐다면 업종 안에서는 약한 종목일 수 있습니다. StockScope는 OpenDART 업종코드를 KRX 업종지수 후보에 매핑한 뒤 같은 거래일 EOD를 비교합니다.",
    read: "시장과 업종을 둘 다 이기면 상대적인 주도력이 강하고, 시장만 이기고 업종에는 지면 같은 업종의 더 강한 종목과 비교할 가치가 큽니다.",
    caution: "업종 자동 매핑이 불확실하면 StockScope는 억지로 계산하지 않고 업종 비교를 생략합니다.",
  },
  excess_return: {
    title: "시장 대비 초과수익률",
    short: "종목 수익률에서 같은 기간 시장 수익률을 뺀 값입니다.",
    detail: "종목 +10%, 시장 +4%라면 시장 대비 +6%p 강했다고 표현합니다.",
    read: "양수면 시장보다 강했고, 음수면 시장보다 약했다는 뜻입니다.",
  },
  eod: {
    title: "EOD",
    short: "End Of Day의 약자로 장이 끝난 뒤 확정된 일별 데이터를 뜻합니다.",
    detail: "StockScope의 KRX 데이터는 실시간 체결가가 아니라 확정 일봉을 기본으로 사용합니다.",
    read: "장중 현재가와 다를 수 있으므로 필요하면 현재 참고가격을 따로 입력해 시나리오를 비교합니다.",
  },
  volatility: {
    title: "변동성",
    short: "가격이 얼마나 크게 흔들리는지를 뜻합니다.",
    detail: "변동성이 높으면 짧은 시간에도 수익과 손실 폭이 커질 수 있습니다.",
    read: "변동성이 클수록 손절·목표 구간을 너무 촘촘하게 잡지 않는지 함께 봅니다.",
  },
  higher_low: {
    title: "저점 상승(Higher Low)",
    short: "최근 조정의 바닥이 이전 바닥보다 높아진 상태입니다.",
    detail: "매도 압력이 이전보다 약해지고 매수세가 더 높은 가격에서 들어왔다는 구조적 단서로 봅니다.",
    read: "상승 추세나 눌림목에서는 최근 저점이 계속 높아지는지 중요한 확인 기준으로 사용합니다.",
  },
  higher_high: {
    title: "고점 상승(Higher High)",
    short: "최근 고점이 이전 고점보다 높아진 상태입니다.",
    detail: "상승 추세에서 매수세가 이전 고점을 넘어 새로운 가격대를 만든 구조적 단서입니다.",
    read: "고점과 저점이 함께 높아지면 상승 추세가 유지되는 근거가 더 강해집니다.",
  },
  strategy_score: {
    title: "전략 적합도 점수",
    short: "현재 상태가 해당 전략의 조건과 얼마나 많이 맞는지를 나타내는 점수입니다.",
    detail: "가격, 이동평균선, RSI, 거래량, 상대강도 등 전략별 조건을 점수화합니다.",
    caution: "80점은 '80% 확률로 상승'이라는 뜻이 아닙니다.",
    read: "여러 전략 중 현재 상황에 더 잘 맞는 접근법을 비교하는 용도입니다.",
  },
  fundamental_health: {
    title: "재무 체력",
    short: "회사가 돈을 벌고, 빚을 감당하고, 실제 현금을 만들어내는 힘을 종합해서 보는 결과입니다.",
    detail: "StockScope는 수익성·성장성·재무 안정성·현금흐름을 따로 평가한 뒤 하나의 결과로 요약합니다.",
    read: "주가 흐름이 좋아도 재무 체력이 약하면 단기 모멘텀과 장기 기업가치를 분리해서 보는 것이 좋습니다.",
    caution: "재무 체력이 좋다고 단기 주가 상승이 보장되는 것은 아닙니다.",
  },
  revenue: {
    title: "매출",
    short: "회사가 제품이나 서비스를 팔아 벌어들인 전체 금액입니다.",
    detail: "매출은 회사의 외형을 보여줍니다. 하지만 매출이 늘어도 비용이 더 빨리 늘면 이익은 줄 수 있습니다.",
    read: "매출 증가와 영업이익 증가가 함께 나타나는지 보는 것이 중요합니다.",
  },
  operating_profit: {
    title: "영업이익",
    short: "회사가 본업으로 실제 얼마를 벌었는지 보여주는 이익입니다.",
    detail: "매출에서 제품 원가, 인건비, 판매관리비처럼 본업에 필요한 비용을 뺀 결과입니다.",
    read: "매출보다 영업이익이 더 빠르게 늘면 수익성이 좋아지고 있을 가능성이 있습니다.",
  },
  net_income: {
    title: "당기순이익",
    short: "세금과 이자 등까지 모두 반영한 뒤 최종적으로 남은 이익입니다.",
    detail: "본업 외 손익과 세금까지 포함하므로 주주에게 귀속되는 최종 이익에 가깝습니다.",
    read: "순이익이 흑자인지뿐 아니라 영업현금흐름도 같은 방향인지 함께 봅니다.",
  },
  operating_margin: {
    title: "영업이익률",
    short: "매출 100원 중 본업으로 몇 원을 남겼는지 나타냅니다.",
    detail: "영업이익 ÷ 매출 × 100으로 계산합니다.",
    read: "같은 회사에서 이익률이 여러 해에 걸쳐 높아지는지 보면 수익성 개선 여부를 알기 쉽습니다.",
  },
  roe: {
    title: "ROE",
    short: "주주가 투자한 자기자본으로 회사가 얼마나 효율적으로 이익을 냈는지 나타냅니다.",
    detail: "순이익을 평균 자기자본으로 나눠 계산합니다. 예를 들어 ROE 15%는 자기자본 100원으로 약 15원의 이익을 냈다는 뜻입니다.",
    read: "높은 값 하나보다 여러 해 동안 안정적으로 유지되거나 개선되는지가 더 중요합니다.",
    caution: "부채를 많이 쓰면 ROE가 높아질 수도 있으므로 부채비율과 함께 봅니다.",
  },
  roa: {
    title: "ROA",
    short: "회사가 보유한 전체 자산으로 얼마나 효율적으로 이익을 냈는지 나타냅니다.",
    detail: "순이익을 평균 총자산으로 나눠 계산합니다.",
    read: "ROE와 함께 보면 부채를 포함한 전체 자산 활용 효율을 더 균형 있게 볼 수 있습니다.",
  },
  eps: {
    title: "EPS",
    short: "주식 1주가 만들어낸 순이익입니다.",
    detail: "일반적으로 순이익을 주식 수로 나눠 계산합니다. StockScope는 DART 보고값을 우선하고 없으면 현재 상장주식수로 근사합니다.",
    read: "PER 계산의 분모로 사용합니다. EPS가 적자면 일반적인 PER 해석이 어렵습니다.",
  },
  bps: {
    title: "BPS",
    short: "회사 순자산을 주식 1주당 얼마씩 가지고 있는지 나타낸 값입니다.",
    detail: "자본총계를 주식 수로 나눠 계산합니다.",
    read: "PBR 계산에 사용되며, 업종에 따라 자산의 의미가 크게 다를 수 있습니다.",
  },
  per: {
    title: "PER",
    short: "현재 주가가 1주당 이익의 몇 배 수준인지 나타냅니다.",
    detail: "주가 ÷ EPS로 계산합니다. PER 10배라면 현재 이익이 그대로 유지된다는 단순 가정에서 주가가 연간 이익의 약 10배라는 뜻입니다.",
    read: "낮다고 무조건 싸고 높다고 무조건 비싼 것이 아니라 성장률과 업종을 같이 봐야 합니다.",
    caution: "적자 기업에서는 PER을 일반적으로 해석하기 어렵습니다.",
  },
  pbr: {
    title: "PBR",
    short: "현재 주가가 1주당 순자산의 몇 배인지 나타냅니다.",
    detail: "주가 ÷ BPS로 계산합니다.",
    read: "자산 비중이 큰 업종에서는 참고가 되지만 성장기업·서비스기업은 PBR만으로 평가하기 어렵습니다.",
  },
  debt_ratio: {
    title: "부채비율",
    short: "자기자본에 비해 부채가 얼마나 큰지 보여줍니다.",
    detail: "부채총계 ÷ 자본총계 × 100으로 계산합니다.",
    read: "일반 기업에서는 높아질수록 재무 부담을 더 주의해서 봅니다.",
    caution: "금융업처럼 원래 부채를 사업에 많이 사용하는 업종은 일반 기업과 같은 기준으로 비교하면 안 됩니다.",
  },
  current_ratio: {
    title: "유동비율",
    short: "1년 안에 갚아야 할 부채를 단기 자산으로 얼마나 감당할 수 있는지 보는 값입니다.",
    detail: "유동자산 ÷ 유동부채 × 100으로 계산합니다.",
    read: "100% 아래라고 바로 위험한 것은 아니지만 단기 유동성 여유가 작은지 살펴보는 신호가 됩니다.",
  },
  operating_cash_flow: {
    title: "영업활동현금흐름",
    short: "회사의 본업에서 실제 현금이 들어왔는지 보여줍니다.",
    detail: "회계상 이익과 달리 실제 현금 유입·유출을 반영합니다.",
    read: "순이익은 흑자인데 영업현금흐름이 계속 마이너스라면 이익의 질을 더 확인해야 합니다.",
  },
  free_cash_flow: {
    title: "FCF(잉여현금흐름)",
    short: "본업으로 번 현금에서 설비·무형자산 투자에 쓴 돈을 빼고 남은 현금을 뜻합니다.",
    detail: "StockScope는 DART에서 유형·무형자산 취득액을 확인할 수 있을 때 영업현금흐름에서 이를 빼 근사합니다.",
    read: "플러스가 지속되면 사업 유지와 투자 후에도 현금 여력이 남는다는 긍정적인 단서가 될 수 있습니다.",
    caution: "대규모 투자 시기에는 좋은 기업도 일시적으로 FCF가 낮아질 수 있습니다.",
  },
  market_cap: {
    title: "시가총액",
    short: "시장 가격으로 본 회사 전체 주식의 가치입니다.",
    detail: "주가 × 상장주식수로 계산합니다.",
    read: "기업 규모를 비교할 때 사용하며 회사의 장부상 자본과는 다른 개념입니다.",
  },
  value_investing: {
    title: "가치투자",
    short: "회사의 가치에 비해 현재 가격이 충분히 싼지를 중요하게 보는 투자 방식입니다.",
    detail: "PER·PBR 같은 가격 배수만 보는 것이 아니라 이익 지속성, 부채, 현금흐름과 함께 가격의 여유를 확인합니다.",
    read: "좋은 회사라도 너무 비싸면 기다리고, 인기 없는 회사라도 가치 대비 충분히 싸면 검토할 수 있습니다.",
    caution: "주가가 많이 떨어졌다는 사실만으로 가치투자 대상이 되는 것은 아닙니다.",
  },
  growth_investing: {
    title: "성장투자",
    short: "매출과 이익이 빠르게 커지는 기업의 성장 지속성에 투자하는 방식입니다.",
    detail: "현재 이익보다 앞으로 이익이 얼마나 커질 수 있는지를 중요하게 보지만, 성장 기대가 이미 가격에 과도하게 반영됐는지도 함께 봐야 합니다.",
    read: "최근 분기 성장과 연간 성장의 지속성, 부채와 현금흐름을 함께 확인합니다.",
  },
  margin_of_safety: {
    title: "안전마진",
    short: "내가 생각하는 기업 가치보다 충분히 낮은 가격에서 여유를 두고 접근하려는 개념입니다.",
    detail: "분석이 조금 틀리거나 예상치 못한 악재가 생겨도 손실 위험을 줄이기 위해 가격에 완충구간을 두는 생각입니다.",
    read: "Graham식 가치투자에서는 기업이 괜찮은지만큼 '얼마나 싸게 사는가'가 중요합니다.",
    caution: "StockScope의 PER·PBR은 안전마진을 완전히 계산한 내재가치 모델이 아니라 참고 배수입니다.",
  },
  economic_moat: {
    title: "경제적 해자",
    short: "경쟁사가 쉽게 빼앗기 어려운 기업의 지속적인 경쟁우위를 뜻합니다.",
    detail: "브랜드, 네트워크 효과, 비용 우위, 전환비용 같은 요소가 예시입니다. StockScope의 현재 재무 API만으로 해자를 완전히 판정할 수는 없습니다.",
    read: "Buffett식 장기투자에서는 높은 수익성이 오랫동안 유지되는 이유가 무엇인지 함께 보는 개념입니다.",
  },
  peg: {
    title: "PEG",
    short: "PER을 이익 성장률과 함께 비교해 성장에 비해 가격이 비싼지 보는 참고 지표입니다.",
    detail: "간단히 PER ÷ 이익 성장률로 계산합니다. 예를 들어 PER 20배, 이익 성장률 20%라면 PEG는 약 1입니다.",
    read: "Peter Lynch 관점에서는 성장률이 높은 회사라면 어느 정도 높은 PER도 정당화될 수 있는지 비교하는 보조도구로 쓸 수 있습니다.",
    caution: "한 분기 성장률처럼 변동이 큰 숫자로 PEG를 계산하면 왜곡될 수 있어 장기 성장 추세와 함께 봐야 합니다.",
  },
  earnings_quality: {
    title: "이익의 질",
    short: "회계상 순이익이 실제 영업현금 유입으로 얼마나 잘 이어지는지를 보는 개념입니다.",
    detail: "순이익은 흑자인데 영업현금흐름이 계속 약하면 장부상 이익과 실제 현금 창출 사이에 차이가 있을 수 있습니다.",
    read: "StockScope는 영업현금흐름과 순이익의 관계를 장기 기업 품질 판단에 활용합니다.",
  },
  can_slim: {
    title: "CAN SLIM",
    short: "최근 실적 성장과 시장 주도력, 거래량, 시장 방향을 함께 보는 성장·모멘텀 투자 프레임입니다.",
    detail: "C는 최근 실적, A는 연간 실적, N은 새로운 재료, S는 수요, L은 주도력, I는 기관 후원, M은 시장 방향을 뜻합니다.",
    read: "좋은 재무만으로 충분하지 않고 실제 시장에서 강하게 움직이는 주도주인지 확인하는 데 초점이 있습니다.",
    caution: "현재 StockScope는 기관 후원(I)을 신뢰성 있게 수집하지 않으므로 UNKNOWN으로 표시합니다.",
  },
  investment_style_fit: {
    title: "투자 스타일 적합도",
    short: "현재 종목 데이터가 특정 투자 철학의 조건과 얼마나 잘 맞는지를 비교한 점수입니다.",
    detail: "Buffett, Graham, Peter Lynch, CAN SLIM의 널리 알려진 철학을 StockScope가 가진 재무·상대강도·시장 데이터를 이용해 규칙화한 결과입니다.",
    read: "어떤 관점으로 종목을 볼지 비교하는 용도이며, 선택한 스타일에 따라 중요하게 보는 조건이 달라집니다.",
    caution: "80점은 80% 상승확률이나 실제 투자자의 매수 판단을 뜻하지 않습니다. 평가할 수 없는 조건은 0점이 아니라 UNKNOWN으로 따로 표시합니다.",
  },
  event_impact: {
    title: "공시 영향(Event Impact)",
    short: "최근 공시가 기업과 주가 판단에 긍정·부정·혼재 중 어떤 영향을 줄 수 있는지 정리한 결과입니다.",
    detail: "공시 제목만 보는 것이 아니라 가능한 경우 계약 규모, 발행 규모, 자금 목적, 최근 매출과의 비교 등을 함께 봅니다.",
    caution: "자동 분석이 공시의 모든 법적·회계적 의미를 완벽하게 해석하는 것은 아닙니다.",
    read: "중요 공시는 원문과 함께 확인하는 것이 안전합니다.",
  },
};

export function TermHelp({
  term,
  current,
}: {
  term: TermKey;
  current?: string | null;
}) {
  const item = TERM_DEFINITIONS[term];
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLSpanElement | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const popoverId = useId();

  useEffect(() => {
    if (!open) return;

    const closeFromOutside = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (!target) return;
      if (rootRef.current?.contains(target)) return;
      setOpen(false);
    };

    const closeFromEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      buttonRef.current?.focus();
    };

    document.addEventListener("pointerdown", closeFromOutside, true);
    document.addEventListener("keydown", closeFromEscape);

    return () => {
      document.removeEventListener("pointerdown", closeFromOutside, true);
      document.removeEventListener("keydown", closeFromEscape);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;

    const closeOtherHelp = (event: Event) => {
      const custom = event as CustomEvent<string>;
      if (custom.detail !== popoverId) setOpen(false);
    };

    window.addEventListener("stockscope:term-help-open", closeOtherHelp);
    return () => window.removeEventListener("stockscope:term-help-open", closeOtherHelp);
  }, [open, popoverId]);

  useEffect(() => {
    if (!open || !popoverRef.current || !buttonRef.current) return;

    const reposition = () => {
      const popover = popoverRef.current;
      const button = buttonRef.current;
      if (!popover || !button) return;

      const buttonRect = button.getBoundingClientRect();
      const popoverRect = popover.getBoundingClientRect();
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;
      const gap = 7;
      const edge = 10;

      let left = buttonRect.left;
      let top = buttonRect.bottom + gap;

      if (left + popoverRect.width > viewportWidth - edge) {
        left = Math.max(edge, viewportWidth - popoverRect.width - edge);
      }
      if (left < edge) left = edge;

      if (top + popoverRect.height > viewportHeight - edge) {
        const above = buttonRect.top - popoverRect.height - gap;
        top = above >= edge ? above : Math.max(edge, viewportHeight - popoverRect.height - edge);
      }

      popover.style.left = `${Math.round(left)}px`;
      popover.style.top = `${Math.round(top)}px`;
    };

    reposition();
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);

    return () => {
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
    };
  }, [open]);

  const toggle = () => {
    setOpen((currentOpen) => {
      const nextOpen = !currentOpen;
      if (nextOpen) {
        window.dispatchEvent(new CustomEvent("stockscope:term-help-open", { detail: popoverId }));
      }
      return nextOpen;
    });
  };

  return (
    <span className="term-help" ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className="term-help-trigger"
        aria-label={`${item.title} 설명 ${open ? "닫기" : "보기"}`}
        aria-expanded={open}
        aria-controls={popoverId}
        title={`${item.title} 쉽게 설명`}
        onClick={toggle}
      >
        ?
      </button>

      {open && (
        <div
          ref={popoverRef}
          id={popoverId}
          className="term-help-content"
          role="dialog"
          aria-label={`${item.title} 쉬운 설명`}
        >
          <div className="term-help-header">
            <strong>{item.title}</strong>
            <button type="button" onClick={() => setOpen(false)} aria-label="도움말 닫기">×</button>
          </div>
          <p className="term-help-short">{item.short}</p>
          {current && (
            <div className="term-help-current">
              <b>지금 값은?</b>
              <span>{current}</span>
            </div>
          )}
          <div className="term-help-detail">
            <b>조금 더 자세히</b>
            <p>{item.detail}</p>
          </div>
          <div className="term-help-read">
            <b>어떻게 보면 되나?</b>
            <p>{item.read}</p>
          </div>
          {item.caution && (
            <div className="term-help-caution">
              <b>주의</b>
              <p>{item.caution}</p>
            </div>
          )}
        </div>
      )}
    </span>
  );
}

function metricCard(
  title: string,
  value: ReactNode,
  explanation: string,
  term: TermKey,
) {
  return (
    <article className="beginner-metric-card" key={title}>
      <div className="beginner-metric-title">
        <span>{title}</span>
        <TermHelp term={term} current={explanation} />
      </div>
      <strong>{value}</strong>
      <p>{explanation}</p>
    </article>
  );
}

function maInterpretation(price: number, ma20: number | null) {
  if (ma20 == null || ma20 <= 0) return "20일 평균과 비교할 데이터가 부족합니다.";
  const gap = ((price / ma20) - 1) * 100;
  if (gap >= 3) return `현재가는 20일 평균보다 ${gap.toFixed(1)}% 위입니다. 단기 흐름은 강하지만 평균에서 많이 멀어졌는지도 같이 봅니다.`;
  if (gap >= 0) return `현재가는 20일 평균보다 ${gap.toFixed(1)}% 위입니다. 단기 상승 흐름이 아직 유지되는 쪽입니다.`;
  if (gap > -3) return `현재가는 20일 평균보다 ${Math.abs(gap).toFixed(1)}% 아래입니다. 20일선을 다시 회복하는지 확인할 구간입니다.`;
  return `현재가는 20일 평균보다 ${Math.abs(gap).toFixed(1)}% 아래입니다. 단기 추세가 약해졌을 가능성을 다른 구조와 함께 확인합니다.`;
}

function rsiInterpretation(value: number | null) {
  if (value == null) return "RSI를 계산할 데이터가 부족합니다.";
  if (value >= 70) return `RSI ${value.toFixed(1)}로 과열 구간입니다. 상승 힘은 강하지만 단기 추격 부담도 커질 수 있습니다.`;
  if (value >= 60) return `RSI ${value.toFixed(1)}로 상승 힘이 강한 편입니다. 아직 전형적인 과열 기준 70 아래입니다.`;
  if (value >= 40) return `RSI ${value.toFixed(1)}로 상승·하락 힘이 크게 치우치지 않은 중립권입니다.`;
  if (value >= 30) return `RSI ${value.toFixed(1)}로 매도 힘이 강한 편이며 과매도 구간에 가까워지고 있습니다.`;
  return `RSI ${value.toFixed(1)}로 과매도 구간입니다. 많이 내려왔다는 뜻이지 반등이 보장된다는 뜻은 아닙니다.`;
}

function atrInterpretation(value: number | null) {
  if (value == null) return "ATR 변동폭 데이터가 부족합니다.";
  if (value >= 5) return `최근 하루 평균 실제 변동폭이 주가의 약 ${value.toFixed(1)}%로 매우 큰 편입니다. 손절·목표 간격을 좁게 잡으면 쉽게 흔들릴 수 있습니다.`;
  if (value >= 3) return `최근 하루 평균 실제 변동폭이 약 ${value.toFixed(1)}%로 비교적 큰 편입니다.`;
  if (value >= 1.5) return `최근 하루 평균 실제 변동폭이 약 ${value.toFixed(1)}% 수준입니다.`;
  return `최근 하루 평균 실제 변동폭이 약 ${value.toFixed(1)}%로 비교적 잔잔한 편입니다.`;
}

function volumeInterpretation(value: number | null) {
  if (value == null) return "현재 거래량 비교 데이터가 부족합니다.";
  if (value >= 2) return `최근 20일 평균의 ${value.toFixed(2)}배입니다. 평소보다 거래가 매우 많이 몰린 상태입니다.`;
  if (value >= 1.3) return `최근 20일 평균의 ${value.toFixed(2)}배로 평소보다 거래가 활발합니다.`;
  if (value >= 0.7) return `최근 20일 평균의 ${value.toFixed(2)}배로 대체로 평소 수준입니다.`;
  return `최근 20일 평균의 ${value.toFixed(2)}배로 거래 참여가 평소보다 적습니다.`;
}

function supportInterpretation(distance: number | null) {
  if (distance == null) return "현재가와 지지 후보의 거리를 계산할 수 없습니다.";
  if (distance < 0) return `현재가가 지지 후보보다 ${Math.abs(distance).toFixed(1)}% 아래입니다. 기존 지지가 이미 깨졌을 가능성을 먼저 확인해야 합니다.`;
  if (distance <= 2) return `현재가가 지지 후보에서 약 ${distance.toFixed(1)}% 위라 지지 유지 여부를 가까이에서 확인할 수 있는 구간입니다.`;
  if (distance <= 5) return `현재가가 지지 후보보다 약 ${distance.toFixed(1)}% 위입니다. 아직 지지와 비교적 가까운 편입니다.`;
  return `현재가가 지지 후보보다 약 ${distance.toFixed(1)}% 위라 당장 지지선 근처라고 보긴 어렵습니다.`;
}

function resistanceInterpretation(distance: number | null) {
  if (distance == null) return "현재가와 저항 후보의 거리를 계산할 수 없습니다.";
  if (distance < 0) return `현재가가 기존 저항 후보를 약 ${Math.abs(distance).toFixed(1)}% 넘어선 상태입니다. 돌파가 유지되는지 확인합니다.`;
  if (distance <= 2) return `현재가가 저항 후보까지 약 ${distance.toFixed(1)}% 남았습니다. 돌파 여부를 곧 확인할 수 있는 구간입니다.`;
  if (distance <= 5) return `저항 후보까지 약 ${distance.toFixed(1)}% 남아 있어 목표·돌파 가능성을 함께 봅니다.`;
  return `저항 후보까지 약 ${distance.toFixed(1)}% 남아 있습니다. 아직 바로 저항에 부딪히는 위치는 아닙니다.`;
}

export function BeginnerIndicatorSummary({
  price,
  ma20,
  rsi14,
  atrPct,
  volumeRatio20,
  support,
  resistance,
  supportDistancePct,
  resistanceDistancePct,
}: {
  price: number;
  ma20: number | null;
  rsi14: number | null;
  atrPct: number | null;
  volumeRatio20: number | null;
  support: number | null;
  resistance: number | null;
  supportDistancePct: number | null;
  resistanceDistancePct: number | null;
}) {
  return (
    <section className="beginner-summary-panel">
      <div className="beginner-summary-head">
        <div>
          <span>BEGINNER EXPLANATION · v0.16.2</span>
          <h3>지금 지표를 쉬운 말로 번역하면</h3>
          <p>숫자를 외울 필요 없이, 현재 값이 어떤 상태를 뜻하는지 먼저 보세요.</p>
        </div>
        <b>초보자 보기</b>
      </div>

      <div className="beginner-metric-grid">
        {metricCard("20일선", ma20 == null ? "-" : `${Math.round(ma20).toLocaleString("ko-KR")}원`, maInterpretation(price, ma20), "ma")}
        {metricCard("RSI", rsi14 == null ? "-" : rsi14.toFixed(1), rsiInterpretation(rsi14), "rsi")}
        {metricCard("ATR", atrPct == null ? "-" : `${atrPct.toFixed(2)}%`, atrInterpretation(atrPct), "atr")}
        {metricCard("거래량", volumeRatio20 == null ? "-" : `${volumeRatio20.toFixed(2)}배`, volumeInterpretation(volumeRatio20), "volume_ratio")}
        {metricCard("지지선", support == null ? "-" : `${Math.round(support).toLocaleString("ko-KR")}원`, supportInterpretation(supportDistancePct), "support")}
        {metricCard("저항선", resistance == null ? "-" : `${Math.round(resistance).toLocaleString("ko-KR")}원`, resistanceInterpretation(resistanceDistancePct), "resistance")}
      </div>
    </section>
  );
}

const GLOSSARY_GROUPS: Array<{ title: string; terms: TermKey[] }> = [
  { title: "가격과 추세", terms: ["ma", "support", "resistance", "trend", "higher_low", "higher_high"] },
  { title: "기술 지표", terms: ["rsi", "overbought", "oversold", "atr", "volatility", "volume_ratio", "momentum"] },
  { title: "전략", terms: ["breakout", "pullback", "strategy_score", "relative_strength", "sector_relative_strength", "excess_return"] },
  { title: "위험 관리", terms: ["invalidation", "stop", "target", "risk_reward", "risk_gate"] },
  { title: "재무·가치평가", terms: ["fundamental_health", "revenue", "operating_profit", "net_income", "operating_margin", "roe", "roa", "debt_ratio", "current_ratio", "operating_cash_flow", "free_cash_flow", "eps", "bps", "per", "pbr", "market_cap"] },
  { title: "투자 철학", terms: ["investment_style_fit", "value_investing", "growth_investing", "margin_of_safety", "economic_moat", "peg", "earnings_quality", "can_slim"] },
  { title: "데이터·공시", terms: ["eod", "event_impact"] },
];

export function BeginnerGlossary() {
  return (
    <details className="beginner-glossary">
      <summary>
        <span>
          <strong>처음 보는 용어가 있나요?</strong>
          <small>RSI, 지지선, ROE, PER, R:R 같은 핵심 용어 전체 사전</small>
        </span>
        <b>용어 사전 보기</b>
      </summary>
      <div className="beginner-glossary-body">
        {GLOSSARY_GROUPS.map((group) => (
          <section key={group.title}>
            <h4>{group.title}</h4>
            <div className="beginner-glossary-grid">
              {group.terms.map((term) => {
                const item = TERM_DEFINITIONS[term];
                return (
                  <article key={term}>
                    <strong>{item.title}</strong>
                    <p>{item.short}</p>
                    <details>
                      <summary>자세히</summary>
                      <div>
                        <p>{item.detail}</p>
                        <b>어떻게 보면 되나?</b>
                        <p>{item.read}</p>
                        {item.caution && (
                          <>
                            <b>주의</b>
                            <p>{item.caution}</p>
                          </>
                        )}
                      </div>
                    </details>
                  </article>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </details>
  );
}
