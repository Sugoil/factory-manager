"""Rate-limited collector for user-registered Naver Real Estate search URLs."""

import csv
import json
import re
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import quote_plus

import requests

from db_store import (
    DB_FILE,
    add_log as db_add_log,
    init_db,
    load_conditions as db_load_conditions,
    load_listings as db_load_listings,
    replace_conditions as db_replace_conditions,
    replace_listings as db_replace_listings,
)


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
    "auto_collected", "collected_at", "source_search_url", "collection_condition", "extraction_status",
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
        (["빌라", "다세대", "주택"], "빌라"), (["오피스텔"], "오피스텔"),
        (["사무실", "오피스"], "사무실"), (["분양권"], "분양권"),
        (["재개발"], "재개발"),
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


def normalize_condition(condition):
    item = dict(condition)
    item["regions"] = item.get("regions") or [item.get("region", "충북 전체")]
    item["property_types"] = item.get("property_types") or [item.get("property_type", "전체")]
    item["deal_types"] = item.get("deal_types") or [item.get("deal_type", "전체")]
    if "전체" in item["property_types"]:
        item["property_types"] = ["전체"]
    if "전체" in item["deal_types"]:
        item["deal_types"] = ["전체"]
    item["enabled"] = bool(item.get("enabled", True))
    item["registered_at"] = item.get("registered_at", "")
    item["last_collected_at"] = item.get("last_collected_at", "")
    item["new_listing_count"] = int(item.get("new_listing_count", 0) or 0)
    return item


def build_search_url(condition):
    keywords = []
    keywords.extend(condition["regions"])
    keywords.extend([] if "전체" in condition["property_types"] else condition["property_types"])
    keywords.extend([] if "전체" in condition["deal_types"] else condition["deal_types"])
    return f"https://new.land.naver.com/search?keyword={quote_plus(' '.join(keywords))}"


def matches_condition(row, condition):
    address = str(row.get("주소", ""))
    regions = condition["regions"]
    region_match = False
    for region in regions:
        if region == "충북 전체" and ("충청북도" in address or "충북" in address):
            region_match = True
        elif region == "청주시 전체" and "청주시" in address:
            region_match = True
        elif region in address:
            region_match = True
    if regions and not region_match:
        return False

    selected_types = condition["property_types"]
    row_type = row.get("매물종류", "기타")
    if "전체" not in selected_types:
        allowed_types = set(selected_types)
        if "빌라/주택" in allowed_types:
            allowed_types.update(["빌라", "주택"])
        if row_type not in allowed_types:
            return False
    if "전체" not in condition["deal_types"] and row.get("거래유형") not in condition["deal_types"]:
        return False
    price = float(row.get("매매가(만원)", 0) or row.get("전세금(만원)", 0) or 0)
    if condition.get("min_price", 0) and price < float(condition["min_price"]):
        return False
    if condition.get("max_price", 0) and price > float(condition["max_price"]):
        return False
    return True


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
    jeonse = re.search(r"(?:전세금|전세가?|전세)\s*[:：]?\s*([\d,.억천만\s]+)", text)
    deposit = re.search(r"보증금\s*[:：]?\s*([\d,.억천만\s]+)", text)
    rent = re.search(r"월세\s*[:：]?\s*([\d,.억천만\s]+)", text)
    maintenance = re.search(r"관리비\s*[:：]?\s*([\d,.억천만\s]+)", text)
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
    property_type = normalize_type(text)
    if property_type == "기타" and len(condition["property_types"]) == 1:
        selected_type = condition["property_types"][0]
        property_type = "빌라" if selected_type == "빌라/주택" else selected_type
    deal_type = normalize_deal(text)
    if len(condition["deal_types"]) == 1 and condition["deal_types"][0] != "전체":
        deal_type = condition["deal_types"][0]
    sale_price = parse_price(sale.group(1)) if sale else 0
    area_value = parse_price(area.group(1)) if area else 0
    ai_summary = (
        f"■ 핵심 정보\n- 매물종류: {property_type}\n- 거래유형: {deal_type}\n"
        f"- 가격: {sale_price:,.0f}만원\n- 면적: {area_value:,.2f}㎡\n\n"
        "■ 단점/체크사항\n- 자동수집 정보이므로 상세 내용과 현장 상태 확인 필요\n\n"
        "■ 한줄평\n- 추가 확인 후 투자 판단이 필요한 자동수집 매물"
    )
    return {
        "매물명": f"{' '.join(condition['regions'])} {property_type} 자동수집".strip(),
        "주소": address, "지역": address.split()[0] if address else ", ".join(condition["regions"]),
        "매물종류": property_type, "거래유형": deal_type,
        "매매가(만원)": sale_price,
        "전세금(만원)": parse_price(jeonse.group(1)) if jeonse else 0,
        "보증금(만원)": parse_price(deposit.group(1)) if deposit else 0,
        "월세(만원)": parse_price(rent.group(1)) if rent else 0,
        "관리비(만원)": parse_price(maintenance.group(1)) if maintenance else 0,
        "전용면적(㎡)": area_value,
        "네이버부동산 링크": url, "네이버 매물 ID": aid, "naver_url": url,
        "naver_article_id": aid, "auto_collected": "예", "collected_at": now(),
        "source_search_url": condition.get("search_url", ""),
        "collection_condition": (
            f"지역={','.join(condition['regions'])};"
            f"매물종류={','.join(condition['property_types'])};"
            f"거래유형={','.join(condition['deal_types'])}"
        ),
        "extraction_status": "자동수집",
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
    collected_at = now()
    db_add_log(condition.get("id", ""), status, url, message, collected_at)
    exists = LOG_FILE.exists()
    with LOG_FILE.open("a", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["수집시간", "조건ID", "상태", "URL", "메시지"])
        if not exists:
            writer.writeheader()
        writer.writerow({
            "수집시간": collected_at, "조건ID": condition.get("id", ""), "상태": status,
            "URL": url, "메시지": message,
        })


def friendly_error(error, fallback="자동 추출 실패"):
    if isinstance(error, (requests.Timeout, requests.ConnectionError)):
        return "네이버 서버 응답 지연"
    return f"{fallback}: {type(error).__name__}: {error}"


def duplicate_keys(rows):
    keys = set()
    for row in rows:
        aid = row.get("naver_article_id") or row.get("네이버 매물 ID", "")
        url = row.get("naver_url") or row.get("네이버부동산 링크", "")
        combo = "|".join(str(row.get(key, "")) for key in ["주소", "매매가(만원)", "전용면적(㎡)"])
        keys.update(item for item in [f"id:{aid}" if aid else "", f"url:{url}" if url else "", f"combo:{combo}"] if item)
    return keys


def main():
    init_db()
    raw_conditions = db_load_conditions()
    if CONDITIONS_FILE.exists():
        try:
            raw_conditions = json.loads(CONDITIONS_FILE.read_text(encoding="utf-8"))
            db_replace_conditions(raw_conditions)
        except (json.JSONDecodeError, OSError) as error:
            db_add_log("", "조건 저장 실패", "", f"조건 파일 읽기 실패: {error}", now())
    conditions = [normalize_condition(item) for item in raw_conditions]
    for condition in conditions:
        condition["new_listing_count"] = 0
    active_conditions = [item for item in conditions if item.get("enabled", True)]
    if not active_conditions:
        print("auto collect complete: no active conditions")
        return
    rows = db_load_listings()
    csv_rows, columns = load_csv(LISTINGS_FILE)
    if not rows:
        rows = csv_rows
        if rows:
            db_replace_listings(rows)
    columns = list(dict.fromkeys(columns + META_COLUMNS))
    known = duplicate_keys(rows)
    new_rows = []
    updated_existing = False
    with requests.Session() as session:
        session.headers.update(HEADERS)
        for condition in active_conditions:
            if len(new_rows) >= MAX_NEW:
                break
            condition["last_collected_at"] = now()
            try:
                search_url = condition.get("search_url") or build_search_url(condition)
                condition["search_url"] = search_url
                search_html = fetch(session, search_url)
                candidates = discover_urls(search_html)
                append_log(condition, "검색 성공", f"후보 {len(candidates)}개")
            except Exception as error:
                append_log(condition, "검색 실패", friendly_error(error, "자동 추출 실패"), condition.get("search_url", ""))
                continue
            time.sleep(REQUEST_DELAY)
            for url in candidates:
                if len(new_rows) >= MAX_NEW:
                    break
                aid = article_id(url)
                if f"id:{aid}" in known or f"url:{url}" in known:
                    append_log(condition, "중복 매물", "이미 저장된 매물 ID 또는 URL입니다.", url)
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
                        append_log(condition, "중복 매물", "주소 + 가격 + 면적이 같은 매물입니다.", url)
                        continue
                    if not matches_condition(row, condition):
                        continue
                    new_rows.append(row)
                    condition["new_listing_count"] += 1
                    known.update([f"id:{article_id(url)}", f"url:{url}", combo])
                    append_log(condition, "신규 저장", url=url)
                except Exception as error:
                    append_log(condition, "상세 추출 실패", friendly_error(error), url)
                time.sleep(REQUEST_DELAY)
    if new_rows or updated_existing:
        db_replace_listings(rows + new_rows)
        columns = list(dict.fromkeys(columns + [key for row in new_rows for key in row]))
        with LISTINGS_FILE.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows + new_rows)
    CONDITIONS_FILE.write_text(
        json.dumps(conditions, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    db_replace_conditions(conditions)
    print(f"auto collect complete: {len(new_rows)} new listing(s)")


if __name__ == "__main__":
    main()
