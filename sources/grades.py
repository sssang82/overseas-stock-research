"""애널리스트 등급·목표가 변경 (yfinance, 비공식 무료 경로). AI 없이 용어표로 한국어 제목을 만든다."""
from datetime import datetime

import pandas as pd

from sources import item

GRADES = {
    "strong buy": "적극 매수", "buy": "매수", "outperform": "시장 상회", "market outperform": "시장 상회",
    "sector outperform": "업종 상회", "overweight": "비중 확대", "positive": "긍정적", "accumulate": "매집",
    "add": "추가 매수", "hold": "보유", "neutral": "중립", "market perform": "시장 수익률",
    "sector perform": "업종 수익률", "peer perform": "업종 수익률", "in-line": "시장 수익률",
    "equal-weight": "비중 유지", "equal weight": "비중 유지", "sector weight": "비중 유지", "mixed": "중립",
    "underweight": "비중 축소", "underperform": "시장 하회", "sector underperform": "업종 하회",
    "negative": "부정적", "reduce": "비중 축소", "sell": "매도", "strong sell": "적극 매도",
}
ACTIONS = {"up": "상향", "down": "하향", "main": "유지", "reit": "재확인", "init": "신규 커버"}


def _ko(grade: str) -> str:
    return GRADES.get((grade or "").strip().lower(), grade or "")


def fetch(ticker: str, since: datetime) -> list[dict]:
    import yfinance as yf
    df = yf.Ticker(ticker).upgrades_downgrades
    if df is None or df.empty:
        return []
    rows = []
    for when, r in df.iterrows():
        ts = pd.Timestamp(when)
        ts = ts.tz_localize("America/New_York") if ts.tzinfo is None else ts
        if ts < since:
            continue
        firm, to, frm = r.get("Firm", ""), r.get("ToGrade", ""), r.get("FromGrade", "")
        cur, prior = float(r.get("currentPriceTarget") or 0), float(r.get("priorPriceTarget") or 0)
        action = ACTIONS.get(r.get("Action", ""), r.get("Action", ""))
        grade = _ko(to) if not frm or frm == to else f"{_ko(frm)} → {_ko(to)}"
        title_ko = f"{firm}: {grade} ({action})"
        if cur and prior and cur != prior:
            title_ko += f", 목표가 ${prior:,.0f} → ${cur:,.0f}"
        elif cur:
            title_ko += f", 목표가 ${cur:,.0f}"
        title = f"{firm}: {frm + ' -> ' if frm and frm != to else ''}{to} ({r.get('Action', '')})"
        rows.append(item("grade", "yfinance", title, f"https://finance.yahoo.com/quote/{ticker}/analysis",
                         ts.tz_convert("UTC").to_pydatetime(), f"grade:{ts:%Y-%m-%d}:{firm}",
                         publisher=firm, tier="애널리스트", title_ko=title_ko,
                         extra={"to": to, "from": frm, "action": r.get("Action", ""),
                                "target": cur or None, "prior_target": prior or None}))
    return rows
