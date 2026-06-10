"""Rate-limited collector for user-registered Naver Real Estate search URLs."""

import csv
import json
import re
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

import requests


ROOT = Path(__file__).parent
LISTINGS_FILE = ROOT / "listings.csv"
CONDITIONS_FILE = ROOT / "search_conditions.json"
LOG_FILE = ROOT / "collect_logs.csv"
MAX_NEW = 3
REQUEST_DELAY = 10
TIMEOUT = 30
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
    "Referer": "https://new.land.naver.com/",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
}
META_COLUMNS = [
    "네이버부동산 링크", "네이버 매물 ID", "naver_url", "naver_article_id",
    "auto_collected", "collected_at", "source_search_url", "extraction_status",
    "extraction_error", "agency_name", "agency_owner", "agent_name", "agent_phone",
    "office_phone", "mobile_phone", "agency_address", "agency_registration_number",
    "platform", "provider_agency_name", "listing_provider", "is_verified_listing",
    "verified_date", "listed_date", "updated_date", "first_seen_at", "last_seen_at",
    "ai_summary", "ai_strengths",
    "ai_risks", "ai_investment_points", "ai_location_score", "ai_price_score",
    "ai_access_score", "ai_investment_score", "ai_scarcity_score", "ai_total_score",
]


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def article_id(url):
    match = re.search(r"(?:articleNo=|articleId=|/articles/|/article/)(\d+)", str(url))
    return match.group(1) if match else ""


def parse_price(value):
    text = str(value).replace(",", "").replace(" ", "")
    total = 0.0
    for pattern, multiplier in [(r"([\d.]+)억", 10000), (r"([\d.]+)천", 1000), (r"([\d.]+)만", 1)]:
        match = re.search(pattern, text)
        if match:
            total += float(match.group(1)) * multiplier
    if total:
        return total
    match = re.search(r"[\d.]+", text)
    return float(match.group()) if match else 0


def normalize_type(text):
    rules = [
        (["공장"], "공장"), (["창고"], "창고"), (["토지", "대지", "땅"], "토지"),
        (["상가", "점포"], "상가"), (["원룸"], "원룸"), (["투룸"], "투룸"),
        (["쓰리룸", "3룸"], "쓰리룸"), (["아파트"], "아파트"),
        (["빌라", "다세대"], "빌라"), (["오피스텔"], "오피스텔"),
        (["사무실", "오피스"], "사무실"),
    ]
    for words, result in rules:
        if any(word in str(text) for word in words):
            return result
    return "기타"


def normalize_deal(text):
    if re.search(r"매매|매매가|매도가", str(text)):
        return "매매"
    if re.search(r"전세|전세금", str(text)):
        return "전세"
    if re.search(r"월세|보증금", str(text)):
        return "월세"
    return "매매"


def labeled(text, labels):
    pattern = "|".join(re.escape(label) for label in labels)
    match = re.search(rf"(?:{pattern})\s*[:：]?\s*([^\n|]{{2,100}}?)(?=[\n|]|$)", text)
    return match.group(1).strip() if match else ""


def phone(value):
    match = re.search(r"(?<!\d)(0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4})(?!\d)", str(value))
    return re.sub(r"\s+", "-", match.group(1)) if match else ""


def listing_date(value):
    match = re.search(r"\b(\d{2,4}[./-]\d{1,2}[./-]\d{1,2})\b", str(value))
    return match.group(1) if match else ""


def fetch(session, url):
    last_error = None
    for attempt in range(1, 4):
        try:
            response = session.get(url, timeout=TIMEOUT)
            response.raise_for_status()
            return response.text
        except Exception as error:
            last_error = error
            if attempt < 3:
                time.sleep(2)
    raise last_error


def discover_urls(html):
    decoded = unescape(html).replace("\\u002F", "/").replace("\\/", "/")
    urls = set(re.findall(r"https?://[^\"' <]+", decoded))
    ids = set(re.findall(r'"articleNo"\s*:\s*"?(\d+)"?', decoded))
    urls.update(f"https://new.land.naver.com/articles/{item}" for item in ids)
    return sorted(
        url.rstrip("\\,}")
        for url in urls
        if "new.land.naver.com" in url and article_id(url)
    )


def extract_row(url, html, condition):
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(html))).strip()
    address_match = re.search(
        r"((?:서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|"
        r"울산광역시|세종특별자치시|경기도|강원특별자치도|충청북도|충청남도|"
        r"전북특별자치도|전라남도|경상북도|경상남도|제주특별자치도)\s+[^|]{2,60})",
        text,
    )
    address = address_match.group(1).strip() if address_match else ""
    sale = re.search(r"(?:매매가?|매도가)\s*[:：]?\s*([\d,.억천만\s]+)", text)
    area = re.search(r"(?:전용면적|전용|공급면적|공급|대지면적|대지|건물면적|연면적)\s*[:：]?\s*([\d,.]+)", text)
    aid = article_id(url)
    agency_name = labeled(text, ["중개사무소명", "중개사무소", "부동산명", "상호"])
    office_phone = phone(labeled(text, ["사무실 전화번호", "대표전화", "전화"]))
    mobile_phone = phone(labeled(text, ["휴대폰 번호", "휴대폰", "핸드폰"]))
    agent_phone = phone(labeled(text, ["중개사 연락처", "담당자 연락처", "연락처"]))
    provider_match = re.search(
        r"((?:네이버부동산|부동산써브|직방|다방|한방|부동산114)\s*제공)", text
    )
    observed_at = now()
    property_type = normalize_type(f"{condition.get('property_type', '')} {text}")
    deal_type = normalize_deal(f"{condition.get('deal_type', '')} {text}")
    sale_price = parse_price(sale.group(1)) if sale else 0
    area_value = parse_price(area.group(1)) if area else 0
    ai_summary = (
        f"■ 핵심 정보\n- 매물종류: {property_type}\n- 거래유형: {deal_type}\n"
        f"- 가격: {sale_price:,.0f}만원\n- 면적: {area_value:,.2f}㎡\n\n"
        "■ 단점/체크사항\n- 자동수집 정보이므로 상세 내용과 현장 상태 확인 필요\n\n"
        "■ 한줄평\n- 추가 확인 후 투자 판단이 필요한 자동수집 매물"
    )
    return {
        "매물명": f"{condition.get('region', '')} {condition.get('property_type', '기타')} 자동수집".strip(),
        "주소": address, "지역": address.split()[0] if address else condition.get("region", ""),
        "매물종류": property_type, "거래유형": deal_type,
        "매매가(만원)": sale_price, "전용면적(㎡)": area_value,
        "네이버부동산 링크": url, "네이버 매물 ID": aid, "naver_url": url,
        "naver_article_id": aid, "auto_collected": "예", "collected_at": now(),
        "source_search_url": condition.get("search_url", ""), "extraction_status": "자동수집",
        "extraction_error": "", "매물 상태": "신규",
        "agency_name": agency_name, "agency_owner": labeled(text, ["대표자명", "대표자"]),
        "agent_name": labeled(text, ["매물 담당자명", "중개사명", "담당자"]),
        "agent_phone": agent_phone, "office_phone": office_phone, "mobile_phone": mobile_phone,
        "agency_address": labeled(text, ["중개사무소 주소", "사무실 주소"]),
        "agency_registration_number": labeled(text, ["중개사무소 등록번호", "등록번호"]),
        "platform": "네이버부동산",
        "provider_agency_name": labeled(text, ["제공 부동산명", "제공 부동산"]),
        "listing_provider": labeled(text, ["매물 제공처", "제공처"])
        or (provider_match.group(1) if provider_match else ""),
        "is_verified_listing": "확인매물" if re.search(r"확인매물|확인 매물", text) else "",
        "verified_date": listing_date(labeled(text, ["확인일", "확인매물일"])),
        "listed_date": listing_date(labeled(text, ["등록일", "최초 등록일"])),
        "updated_date": listing_date(labeled(text, ["수정일", "업데이트일", "최종 수정일"])),
        "first_seen_at": observed_at, "last_seen_at": observed_at,
        "ai_summary": ai_summary, "ai_strengths": "", "ai_risks": "상세 내용과 현장 상태 확인 필요",
        "ai_investment_points": "추가 확인 후 투자 판단 필요", "ai_location_score": 55,
        "ai_price_score": 55, "ai_access_score": 50, "ai_investment_score": 50,
        "ai_scarcity_score": 55, "ai_total_score": 53,
    }


def load_csv(path):
    if not path.exists():
        return [], []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader), list(reader.fieldnames or [])


def append_log(condition, status, message="", url=""):
    exists = LOG_FILE.exists()
    with LOG_FILE.open("a", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["수집시간", "조건ID", "상태", "URL", "메시지"])
        if not exists:
            writer.writeheader()
        writer.writerow({
            "수집시간": now(), "조건ID": condition.get("id", ""), "상태": status,
            "URL": url, "메시지": message,
        })


def duplicate_keys(rows):
    keys = set()
    for row in rows:
        aid = row.get("naver_article_id") or row.get("네이버 매물 ID", "")
        url = row.get("naver_url") or row.get("네이버부동산 링크", "")
        combo = "|".join(str(row.get(key, "")) for key in ["주소", "매매가(만원)", "전용면적(㎡)"])
        keys.update(item for item in [f"id:{aid}" if aid else "", f"url:{url}" if url else "", f"combo:{combo}"] if item)
    return keys


def main():
    conditions = json.loads(CONDITIONS_FILE.read_text(encoding="utf-8")) if CONDITIONS_FILE.exists() else []
    active_conditions = [item for item in conditions if item.get("enabled", True)]
    if not active_conditions:
        print("auto collect complete: no active conditions")
        return
    rows, columns = load_csv(LISTINGS_FILE)
    columns = list(dict.fromkeys(columns + META_COLUMNS))
    known = duplicate_keys(rows)
    new_rows = []
    updated_existing = False
    with requests.Session() as session:
        session.headers.update(HEADERS)
        for condition in active_conditions:
            if len(new_rows) >= MAX_NEW:
                break
            try:
                search_html = fetch(session, condition["search_url"])
                candidates = discover_urls(search_html)
                append_log(condition, "검색 성공", f"후보 {len(candidates)}개")
            except Exception as error:
                append_log(condition, "검색 실패", f"{type(error).__name__}: {error}", condition.get("search_url", ""))
                continue
            time.sleep(REQUEST_DELAY)
            for url in candidates:
                if len(new_rows) >= MAX_NEW:
                    break
                aid = article_id(url)
                if f"id:{aid}" in known or f"url:{url}" in known:
                    for existing in rows:
                        existing_id = existing.get("naver_article_id") or existing.get("네이버 매물 ID", "")
                        existing_url = existing.get("naver_url") or existing.get("네이버부동산 링크", "")
                        if (aid and existing_id == aid) or existing_url == url:
                            existing["last_seen_at"] = now()
                            updated_existing = True
                            break
                    continue
                try:
                    row = extract_row(url, fetch(session, url), condition)
                    combo = "combo:" + "|".join(str(row.get(key, "")) for key in ["주소", "매매가(만원)", "전용면적(㎡)"])
                    if combo in known:
                        continue
                    price = float(row.get("매매가(만원)", 0) or 0)
                    if condition.get("min_price", 0) and price < float(condition["min_price"]):
                        continue
                    if condition.get("max_price", 0) and price > float(condition["max_price"]):
                        continue
                    new_rows.append(row)
                    known.update([f"id:{article_id(url)}", f"url:{url}", combo])
                    append_log(condition, "신규 저장", url=url)
                except Exception as error:
                    append_log(condition, "상세 추출 실패", f"{type(error).__name__}: {error}", url)
                time.sleep(REQUEST_DELAY)
    if new_rows or updated_existing:
        columns = list(dict.fromkeys(columns + [key for row in new_rows for key in row]))
        with LISTINGS_FILE.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows + new_rows)
    print(f"auto collect complete: {len(new_rows)} new listing(s)")


if __name__ == "__main__":
    main()
