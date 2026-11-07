"""뉴스와 분석 글 (RSS). 제목·링크·날짜만 받고, 본문은 상세 화면에서 필요할 때 받는다."""
import hashlib
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

from sources import clean, get, item, parse_date

MAJOR = {  # 주요 언론
    "reuters.com": "Reuters", "bloomberg.com": "Bloomberg", "wsj.com": "WSJ", "cnbc.com": "CNBC",
    "barrons.com": "Barron's", "ft.com": "Financial Times", "apnews.com": "AP", "marketwatch.com": "MarketWatch",
    "investors.com": "Investor's Business Daily", "nytimes.com": "New York Times", "finance.yahoo.com": "Yahoo Finance",
    "forbes.com": "Forbes", "fortune.com": "Fortune", "businessinsider.com": "Business Insider", "axios.com": "Axios",
    "economist.com": "The Economist", "washingtonpost.com": "Washington Post", "techcrunch.com": "TechCrunch",
    "theverge.com": "The Verge", "statnews.com": "STAT", "fiercebiotech.com": "Fierce Biotech",
    "electrek.co": "Electrek", "tomshardware.com": "Tom's Hardware",
}
OPINION = {  # 분석·의견 (개인 필자나 투자 정보 사이트)
    "fool.com": "Motley Fool", "seekingalpha.com": "Seeking Alpha", "zacks.com": "Zacks", "benzinga.com": "Benzinga",
    "247wallst.com": "24/7 Wall St.", "trefis.com": "Trefis", "tikr.com": "TIKR", "investorplace.com": "InvestorPlace",
    "gurufocus.com": "GuruFocus", "simplywall.st": "Simply Wall St", "tipranks.com": "TipRanks",
    "insidermonkey.com": "Insider Monkey", "marketbeat.com": "MarketBeat", "thestreet.com": "TheStreet",
    "nasdaq.com": "Nasdaq", "investing.com": "Investing.com", "barchart.com": "Barchart",
}
_NAME_TIER = {**{n.lower(): "주요 언론" for n in MAJOR.values()}, **{n.lower(): "분석·의견" for n in OPINION.values()}}
# 정보가 없는 시세 안내 페이지
JUNK = re.compile(r"stock price, news|stock quote|quote & history|price and forecast|historical prices|"
                  r"options chain|stock price today|real-?time quote|stock chart", re.I)
SA_NEWS_TITLE = re.compile(r"\([A-Z.]+:(NASDAQ|NYSE)[A-Z]*\)")


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    for d in (*MAJOR, *OPINION):
        if host == d or host.endswith("." + d):
            return d
    return host


def publisher_of(url: str = "", name: str = "") -> tuple[str, str]:
    """(작성한 곳, 구분). 링크 주소나 Google 이 알려주는 매체명으로 정한다."""
    if name:
        name = name.removeprefix("The ") if name.lower().removeprefix("the ") in _NAME_TIER else name
        return name, _NAME_TIER.get(name.lower(), "기타")
    d = _domain(url)
    if d in MAJOR:
        return MAJOR[d], "주요 언론"
    if d in OPINION:
        return OPINION[d], "분석·의견"
    return d, "기타"


def title_uid(title: str) -> str:
    """같은 기사가 여러 곳에서 와도 한 건으로 합치도록 제목으로 만든 번호."""
    key = re.sub(r"[^a-z0-9]+", "", title.lower())[:120]
    return "news:" + hashlib.sha1(key.encode()).hexdigest()[:16]


def _rss(url: str, **params) -> list[dict]:
    root = ET.fromstring(get(url, params=params).content)
    out = []
    for it in root.iter("item"):
        src = it.find("source")
        out.append({"title": clean(it.findtext("title")), "link": (it.findtext("link") or "").strip(),
                    "guid": (it.findtext("guid") or "").strip(),
                    "date": parse_date(it.findtext("pubDate")), "summary": clean(it.findtext("description"))[:600],
                    "source": (src.text or "").strip() if src is not None else ""})
    return out


def _rows(entries: list[dict], source: str, kind_of=None) -> list[dict]:
    rows = []
    for e in entries:
        if not e["title"] or not e["link"] or JUNK.search(e["title"]):
            continue
        pub, tier = publisher_of(e["link"], e["source"])
        if kind_of:
            kind = kind_of(e)
        elif pub == "Seeking Alpha" and SA_NEWS_TITLE.search(e["title"]):
            kind = "news"  # Seeking Alpha 의 짧은 속보는 분석 글이 아니라 뉴스
        else:
            kind = "analysis" if tier == "분석·의견" else "news"
        rows.append(item(kind, source, e["title"], e["link"], e["date"], title_uid(e["title"]),
                         publisher=pub, tier=tier, extra={"summary": e["summary"]} if e["summary"] else None))
    return rows


def yahoo(ticker: str) -> list[dict]:
    return _rows(_rss("https://feeds.finance.yahoo.com/rss/2.0/headline", s=ticker, region="US", lang="en-US"),
                 "yahoo")


def google(ticker: str) -> list[dict]:
    entries = _rss("https://news.google.com/rss/search", q=f"{ticker} stock when:14d",
                   hl="en-US", gl="US", ceid="US:en")
    for e in entries:  # Google 은 제목 끝에 ' - 매체명' 을 붙인다
        if e["source"] and e["title"].endswith(" - " + e["source"]):
            e["title"] = e["title"][: -len(e["source"]) - 3]
        e["summary"] = ""
    return _rows(entries, "google")


def nasdaq(ticker: str) -> list[dict]:
    return _rows(_rss("https://www.nasdaq.com/feed/rssoutbound", symbol=ticker), "nasdaq")


def seeking_alpha(ticker: str) -> list[dict]:
    entries = _rss(f"https://seekingalpha.com/api/sa/combined/{ticker}.xml")
    for e in entries:
        e["source"] = "Seeking Alpha"
        # 속보(MarketCurrent)는 link 가 종목 페이지라서 guid 의 번호로 기사 주소를 만든다
        if m := re.search(r"MarketCurrent:(\d+)", e["guid"]):
            e["link"] = f"https://seekingalpha.com/news/{m.group(1)}"
    return _rows(entries, "seekingalpha", lambda e: "analysis" if "/article/" in e["link"] else "news")
