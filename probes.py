"""자료원 접속 시험. 각 시험은 (받은 건수, 메모) 를 돌려주고, 실패하면 예외를 그대로 올린다."""
import datetime as dt
import html
import os
import re
import time

import requests

BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/120 Safari/537.36")
# SEC 는 요청 헤더에 앱 이름과 연락처를 요구한다. 연락처는 나중에 설정값으로 넣는다.
SEC_UA = os.getenv("SEC_USER_AGENT", "OverseasWatchlist research-app")
NVDA_CIK = "0001045810"
CNBC_TV_CHANNEL = "UCrp_UI8XtuYfpiqluWLD7Lw"

_cache: dict = {}


def get(url, ua=BROWSER, **kw):
    r = requests.get(url, headers={"User-Agent": ua}, timeout=25, **kw)
    r.raise_for_status()
    return r


def text_of(page: str) -> str:
    page = re.sub(r"(?is)<(script|style|head).*?</\1>", " ", page)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page))).strip()


def rss_titles(xml: str) -> list[str]:
    items = re.findall(r"(?s)<item>.*?</item>|<entry>.*?</entry>", xml)
    return [html.unescape(m.group(1)).strip() for i in items
            if (m := re.search(r"(?s)<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", i))]


def google_news(query, hl, gl, ceid):
    xml = get("https://news.google.com/rss/search", params={
        "q": f"{query} when:7d", "hl": hl, "gl": gl, "ceid": ceid}).text
    t = rss_titles(xml)
    return len(t), t[0][:60] if t else ""


def sec_submissions():
    d = get(f"https://data.sec.gov/submissions/CIK{NVDA_CIK}.json", SEC_UA).json()
    _cache["sec"] = d
    r = d["filings"]["recent"]
    return len(r["form"]), f"최근 {r['form'][0]} {r['filingDate'][0]}"


def sec_document():
    d = _cache.get("sec") or get(f"https://data.sec.gov/submissions/CIK{NVDA_CIK}.json", SEC_UA).json()
    r = d["filings"]["recent"]
    i = r["form"].index("10-Q")
    acc = r["accessionNumber"][i].replace("-", "")
    page = get(f"https://www.sec.gov/Archives/edgar/data/{int(NVDA_CIK)}/{acc}/{r['primaryDocument'][i]}", SEC_UA).text
    return len(text_of(page).split()), f"10-Q {r['filingDate'][i]} 본문 단어 수"


def yahoo_rss():
    xml = get("https://feeds.finance.yahoo.com/rss/2.0/headline",
              params={"s": "NVDA", "region": "US", "lang": "en-US"}).text
    _cache["yahoo_links"] = re.findall(r"<link>(https?://[^<]+)</link>", xml)[1:]
    t = rss_titles(xml)
    return len(t), t[0][:60] if t else ""


def yahoo_article():
    links = _cache.get("yahoo_links") or []
    for link in links[:3]:
        try:
            r = get(link)
        except requests.RequestException:
            continue
        words = len(text_of(r.text).split())
        if words > 300:
            return words, f"본문 단어 수 ({r.url.split('/')[2]})"
    return 0, "본문을 받은 기사 없음"


def seeking_alpha_rss():
    t = rss_titles(get("https://seekingalpha.com/api/sa/combined/NVDA.xml").text)
    return len(t), t[0][:60] if t else ""


def nasdaq_rss():
    t = rss_titles(get("https://www.nasdaq.com/feed/rssoutbound", params={"symbol": "NVDA"}).text)
    return len(t), t[0][:60] if t else ""


def youtube_rss():
    xml = get("https://www.youtube.com/feeds/videos.xml", params={"channel_id": CNBC_TV_CHANNEL}).text
    _cache["yt_ids"] = re.findall(r"<yt:videoId>(.*?)</yt:videoId>", xml)
    return len(_cache["yt_ids"]), "CNBC Television 새 영상"


def youtube_transcript():
    from youtube_transcript_api import YouTubeTranscriptApi
    ids = _cache.get("yt_ids") or []
    if not ids:
        return 0, "영상 목록 없음"
    t = YouTubeTranscriptApi().fetch(ids[0])
    return len(t.snippets), "자막 문장 수"


def yf_grades():
    import yfinance as yf
    u = yf.Ticker("NVDA").upgrades_downgrades
    n = 0 if u is None else len(u)
    return n, f"최근 {u.index[0]:%Y-%m-%d} {u.iloc[0]['Firm']}" if n else ""


def fool_transcripts():
    page = get("https://www.fool.com/earnings-call-transcripts/").text
    links = sorted(set(re.findall(r"/earnings/call-transcripts/\d{4}/[^\"']+", page)))
    if not links:
        return 0, "녹취록 링크 없음"
    words = len(text_of(get("https://www.fool.com" + links[0]).text).split())
    return words, "녹취록 1건 단어 수"


def cninfo():
    r = requests.post("http://www.cninfo.com.cn/new/hisAnnouncement/query", timeout=25, headers={
        "User-Agent": BROWSER, "X-Requested-With": "XMLHttpRequest"}, data={
        "pageNum": 1, "pageSize": 5, "column": "sse", "tabName": "fulltext", "plate": "sh",
        "stock": "600519,gssh0600519", "isHLtitle": "true"})
    r.raise_for_status()
    j = r.json()
    a = j.get("announcements") or []
    return j.get("totalAnnouncement") or 0, a[0]["announcementTitle"][:40] if a else ""


def tdnet():
    day = dt.date.today()
    while day.weekday() >= 5:
        day -= dt.timedelta(days=1)
    page = get(f"https://www.release.tdnet.info/inbs/I_list_001_{day:%Y%m%d}.html").text
    return len(re.findall(r"\.pdf", page)), f"{day} 적시공시 PDF 링크 수"


def hkex():
    get("https://www1.hkexnews.hk/search/titlesearch.xhtml?lang=en")
    return 1, "검색 페이지 접속만 확인"


PROBES = [
    ("미국", "SEC 공시 목록", sec_submissions),
    ("미국", "SEC 공시 본문", sec_document),
    ("미국", "Yahoo 뉴스 RSS", yahoo_rss),
    ("미국", "Yahoo 뉴스 본문", yahoo_article),
    ("미국", "Google News (영어)", lambda: google_news("NVDA stock", "en-US", "US", "US:en")),
    ("미국", "Seeking Alpha RSS", seeking_alpha_rss),
    ("미국", "Nasdaq RSS", nasdaq_rss),
    ("미국", "애널리스트 등급 (yfinance)", yf_grades),
    ("미국", "Motley Fool 녹취록", fool_transcripts),
    ("공통", "유튜브 채널 목록", youtube_rss),
    ("공통", "유튜브 자막", youtube_transcript),
    ("일본", "Google News (일본어)", lambda: google_news("トヨタ自動車", "ja", "JP", "JP:ja")),
    ("일본", "TDnet 적시공시", tdnet),
    ("중국", "CNINFO 공시", cninfo),
    ("중국", "Google News (중국어)", lambda: google_news("贵州茅台", "zh-CN", "CN", "CN:zh-Hans")),
    ("홍콩", "HKEXnews", hkex),
]


def run_all():
    """시험을 차례로 돌려 한 줄씩 결과를 내놓는다 (화면이 순서대로 채워지도록)."""
    _cache.clear()
    for country, name, fn in PROBES:
        start = time.time()
        try:
            count, note = fn()
            status = "✅" if count else "⚠️"
        except Exception as e:  # 시험 결과로 보여줄 뿐이라 모든 오류를 받는다
            count, status = 0, "❌"
            code = getattr(getattr(e, "response", None), "status_code", None)
            note = f"{type(e).__name__}{f' {code}' if code else ''}: {str(e)[:80]}"
        yield {"국가": country, "자료원": name, "결과": status, "건수": count,
               "초": round(time.time() - start, 1), "메모": note}
        time.sleep(0.3)


if __name__ == "__main__":
    for row in run_all():
        print(row["결과"], row["국가"], row["자료원"], row["건수"], row["초"], row["메모"])
