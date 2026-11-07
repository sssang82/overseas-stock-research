"""SEC EDGAR 공시. 키는 필요 없고, 요청 헤더에 앱 이름과 연락처 이메일을 넣어야 한다 (초당 10회 이하)."""
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime

from core import config
from sources import get, item, parse_date

FORMS = {  # 공시 종류 → (한국어 이름, 자료 종류)
    "10-K": ("사업보고서", "filing"), "10-K/A": ("사업보고서 정정", "filing"),
    "10-Q": ("분기보고서", "filing"), "10-Q/A": ("분기보고서 정정", "filing"),
    "8-K": ("수시공시", "filing"), "8-K/A": ("수시공시 정정", "filing"),
    "20-F": ("연차보고서(해외기업)", "filing"), "6-K": ("수시공시(해외기업)", "filing"),
    "DEF 14A": ("주주총회 위임장", "filing"),
    "3": ("내부자 최초 보유 신고", "insider"), "4": ("내부자 거래", "insider"), "4/A": ("내부자 거래 정정", "insider"),
    "144": ("내부자 매도 예정 신고", "insider"),
}
for _f in ("SC 13D", "SC 13G", "SCHEDULE 13D", "SCHEDULE 13G"):
    FORMS[_f] = ("대주주 지분 신고", "ownership")
    FORMS[_f + "/A"] = ("대주주 지분 변경 신고", "ownership")

ITEMS_8K = {
    "1.01": "주요 계약 체결", "1.02": "주요 계약 종료", "1.05": "사이버보안 사고", "2.01": "인수·처분 완료",
    "2.02": "실적 발표", "2.03": "채무 발생", "2.05": "구조조정 비용", "2.06": "자산 손상",
    "3.01": "상장 관련 통지", "3.02": "미등록 증권 발행", "5.01": "지배권 변동", "5.02": "임원·이사 변동",
    "5.03": "정관 변경", "5.07": "주주총회 결과", "7.01": "공정공시", "8.01": "기타 주요 사항",
    "9.01": "재무제표·첨부",
}

TX_CODES = {"P": "매수", "S": "매도", "A": "주식 부여", "M": "옵션 행사", "F": "세금 납부용 처분",
            "G": "증여", "C": "전환", "D": "회사에 반환", "J": "기타"}
MAX_FORM4_DETAILS = 30  # 한 번 업데이트에 내용을 읽을 Form 4 최대 개수 (처음 등록 때 요청이 몰리지 않게)


class _Limiter:
    """여러 종목을 동시에 받아도 SEC 요청이 초당 약 6회를 넘지 않게 한다."""
    def __init__(self, interval: float):
        self.interval, self.lock, self.last = interval, threading.Lock(), 0.0

    def wait(self):
        with self.lock:
            delay = self.last + self.interval - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self.last = time.monotonic()


_limit = _Limiter(0.16)
_tickers: dict = {}


def user_agent() -> str:
    return config.get("SEC_USER_AGENT") or "OverseasWatchlist research-app"


def sec_get(url):
    _limit.wait()
    return get(url, headers={"User-Agent": user_agent(), "Accept-Encoding": "gzip, deflate"})


def lookup(ticker: str) -> tuple[int, str] | None:
    """티커 → (SEC 번호, 회사명). SEC 가 주는 전체 목록을 하루 한 번만 받는다."""
    if not _tickers or time.time() - _tickers["_at"] > 86400:
        data = sec_get("https://www.sec.gov/files/company_tickers.json").json()
        _tickers.clear()
        _tickers.update({v["ticker"].upper(): (int(v["cik_str"]), v["title"]) for v in data.values()})
        _tickers["_at"] = time.time()
    return _tickers.get(ticker.upper())


def _title(form: str, label: str, report_date: str, items_8k: str) -> tuple[str, str]:
    if form.startswith("8-K"):
        names = [ITEMS_8K.get(c.strip(), c.strip()) for c in items_8k.split(",") if c.strip()]
        kind = "earnings" if "2.02" in items_8k else "filing"
        head = "실적 발표" if kind == "earnings" else label
        rest = [n for n in names if n != "실적 발표"]
        return f"{form} {head}" + (f": {', '.join(rest)}" if rest else ""), kind
    if form.startswith(("10-K", "20-F")) and report_date:
        return f"{form} {label} (회계연도 말 {report_date})", "filing"
    if form.startswith("10-Q") and report_date:
        return f"{form} {label} ({report_date} 분기)", "filing"
    return f"{form} {label}", FORMS[form][1]


def _form4_summary(cik: int, acc: str, doc: str) -> dict:
    """Form 4 원본 XML 에서 누가, 무엇을, 몇 주, 얼마에 거래했는지 뽑는다."""
    raw = doc.split("/")[-1]  # 'xslF345X06/파일.xml' 은 보기용 화면, 원본은 같은 이름의 XML
    root = ET.fromstring(sec_get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{raw}").content)
    owner = root.findtext(".//reportingOwner/reportingOwnerId/rptOwnerName", "").strip()
    rel = root.find(".//reportingOwner/reportingOwnerRelationship")
    role = ""
    if rel is not None:
        role = (rel.findtext("officerTitle") or "").strip() or \
            ("이사" if (rel.findtext("isDirector") or "").strip() in ("1", "true") else "") or \
            ("10% 대주주" if (rel.findtext("isTenPercentOwner") or "").strip() in ("1", "true") else "")
    txs = {}
    for tx in root.findall(".//nonDerivativeTable/nonDerivativeTransaction"):
        code = tx.findtext("transactionCoding/transactionCode", "").strip()
        shares = float(tx.findtext("transactionAmounts/transactionShares/value") or 0)
        price = float(tx.findtext("transactionAmounts/transactionPricePerShare/value") or 0)
        t = txs.setdefault(code, {"shares": 0.0, "value": 0.0})
        t["shares"] += shares
        t["value"] += shares * price
    return {"owner": owner, "role": role, "transactions": [
        {"code": c, "action": TX_CODES.get(c, c), "shares": v["shares"],
         "avg_price": round(v["value"] / v["shares"], 2) if v["shares"] and v["value"] else None}
        for c, v in txs.items()]}


def _form4_title(form: str, d: dict) -> str:
    who = d["owner"].title() + (f" ({d['role']})" if d["role"] else "")
    parts = [f"{t['action']} {t['shares']:,.0f}주" + (f" @${t['avg_price']:,.2f}" if t["avg_price"] else "")
             for t in d["transactions"]]
    return f"Form {form} {who}: " + (", ".join(parts) if parts else "파생상품 거래만 있음")


def fetch(ticker: str, cik: int, since: datetime, known: set[str]) -> list[dict]:
    r = sec_get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()["filings"]["recent"]
    rows, form4_left = [], MAX_FORM4_DETAILS
    for i, form in enumerate(r["form"]):
        if form not in FORMS:
            continue
        published = parse_date(r["acceptanceDateTime"][i]) or parse_date(r["filingDate"][i])
        if published is None or published < since:
            continue
        acc_dash = r["accessionNumber"][i]
        uid = f"sec:{acc_dash}"
        if uid in known:
            continue
        acc, doc = acc_dash.replace("-", ""), r["primaryDocument"][i]
        label = FORMS[form][0]
        title, kind = _title(form, label, r["reportDate"][i], r["items"][i])
        extra = {"form": form, "accession": acc_dash, "report_date": r["reportDate"][i],
                 "items": r["items"][i], "description": r["primaryDocDescription"][i],
                 "index_url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{acc_dash}-index.htm"}
        if form.startswith("4") and form4_left > 0:
            form4_left -= 1
            try:
                extra["form4"] = _form4_summary(cik, acc, doc)
                title = _form4_title(form, extra["form4"])
            except Exception as e:  # 내용을 못 읽어도 공시 자체는 목록에 남긴다
                extra["form4_error"] = str(e)[:200]
        rows.append(item(kind, "sec", f"{form} {r['primaryDocDescription'][i] or label}",
                         f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}", published, uid,
                         publisher="SEC", tier="1차 자료", title_ko=title, extra=extra))
    return rows
