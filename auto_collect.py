"""Rate-limited collector for user-registered Naver Real Estate search URLs."""

import csv
import json
import random
import re
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urlencode

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
MAX_CANDIDATES = 10
MAX_REQUESTS_PER_RUN = 2
MIN_RANDOM_DELAY = 10
MAX_RANDOM_DELAY = 30
MAX_ATTEMPTS = 2
TIMEOUT = 30
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
    ),
    "Referer": "https://new.land.naver.com/",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    "Accept": "application/json, text/plain, */*",
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

REGION_CODES = {
    "충북 전체": [
        "4311100000", "4311200000", "4311300000", "4311400000", "4313000000",
        "4315000000", "4372000000", "4373000000", "4374000000", "4374500000",
        "4375000000", "4376000000", "4377000000", "4380000000",
    ],
    "청주시 전체": ["4311100000", "4311200000", "4311300000", "4311400000"],
    "청주시 상당구": ["4311100000"], "청주시 서원구": ["4311200000"],
    "청주시 흥덕구": ["4311300000"], "청주시 청원구": ["4311400000"],
    "충주시": ["4313000000"], "제천시": ["4315000000"], "보은군": ["4372000000"],
    "옥천군": ["4373000000"], "영동군": ["4374000000"], "증평군": ["4374500000"],
    "진천군": ["4375000000"], "괴산군": ["4376000000"], "음성군": ["4377000000"],
    "단양군": ["4380000000"],
}
PROPERTY_TYPE_CODES = {
    "전체": "APT:OPST:VL:OR:DDDGG:SGJT:SMS:GJCG:GM:TJ",
    "아파트": "APT", "오피스텔": "OPST", "빌라": "VL", "원룸": "OR",
    "투룸": "OR", "쓰리룸": "OR", "상가": "SMS", "사무실": "SMS",
    "공장": "GJCG", "창고": "GJCG", "토지": "TJ", "기타": "GM",
}
DEAL_TYPE_CODES = {"전체": "A1:B1:B2", "매매": "A1", "전세": "B1", "월세": "B2"}
ROUTE_TYPE_CODES = {
    "complexes": {
        "전체": "APT:ABYG:JGC:PRE",
        "아파트": "APT",
    },
    "houses": {
        "전체": "VL:DDDGG:JWJT:SGJT:HOJT",
        "빌라": "VL",
        "원룸": "DDDGG",
        "투룸": "DDDGG",
        "쓰리룸": "DDDGG",
    },
    "offices": {
        "전체": "OPST:SMS:GJCG:GM:TJ",
        "오피스텔": "OPST",
        "상가": "SMS",
        "사무실": "SMS",
        "공장": "GJCG",
        "창고": "GJCG",
        "토지": "TJ",
        "기타": "GM",
    },
}
REGION_MAP_CENTERS = {
    "충북 전체": (36.8000, 127.7000, 9),
    "청주시 전체": (36.6424, 127.4890, 12),
    "청주시 상당구": (36.6359, 127.4914, 13),
    "청주시 서원구": (36.6370, 127.4749, 13),
    "청주시 흥덕구": (36.6420, 127.4290, 13),
    "청주시 청원구": (36.7120, 127.4860, 13),
    "충주시": (36.9910, 127.9259, 12),
    "제천시": (37.1326, 128.1910, 12),
    "보은군": (36.4895, 127.7295, 12),
    "옥천군": (36.3064, 127.5713, 12),
    "영동군": (36.1750, 127.7765, 12),
    "증평군": (36.7854, 127.5815, 13),
    "진천군": (36.8554, 127.4356, 12),
    "괴산군": (36.8153, 127.7867, 12),
    "음성군": (36.9403, 127.6905, 12),
    "단양군": (36.9845, 128.3656, 12),
}


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
    """Build a browser-renderable Naver Real Estate map URL.

    Naver does not expose ``/search?keyword=...`` as a valid listing page and
    redirects that legacy URL to ``/404``. Use one of the actual map routes.
    """
    regions = condition.get("regions") or ["충북 전체"]
    property_types = condition.get("property_types") or ["전체"]
    deal_types = condition.get("deal_types") or ["전체"]
    first_region = regions[0]
    latitude, longitude, zoom = REGION_MAP_CENTERS.get(
        first_region, REGION_MAP_CENTERS["충북 전체"]
    )

    selected_types = set(property_types)
    if selected_types and selected_types <= {"아파트"}:
        route = "complexes"
    elif selected_types and selected_types <= {"빌라", "원룸", "투룸", "쓰리룸"}:
        route = "houses"
    else:
        route = "offices"

    route_codes = ROUTE_TYPE_CODES[route]
    type_codes = ":".join(dict.fromkeys(
        code for item in property_types
        for code in route_codes.get(item, route_codes["전체"]).split(":")
    ))
    deal_codes = ":".join(dict.fromkeys(
        code for item in deal_types
        for code in DEAL_TYPE_CODES.get(item, "A1:B1:B2").split(":")
    ))
    params = {
        "ms": f"{latitude},{longitude},{zoom}",
        "a": type_codes,
        "b": deal_codes,
        "e": "RETAIL",
    }
    return f"https://new.land.naver.com/{route}?{urlencode(params, safe=':,')}"


def build_naver_api_urls(condition):
    regions = condition.get("regions") or ["충북 전체"]
    property_types = condition.get("property_types") or ["전체"]
    deal_types = condition.get("deal_types") or ["전체"]
    type_codes = ":".join(dict.fromkeys(
        code for item in property_types for code in PROPERTY_TYPE_CODES.get(item, "GM").split(":")
    ))
    deal_codes = ":".join(dict.fromkeys(
        code for item in deal_types for code in DEAL_TYPE_CODES.get(item, "A1:B1:B2").split(":")
    ))
    urls = []
    for region in regions:
        cortar_numbers = REGION_CODES.get(region, [])
        if not cortar_numbers:
            continue
        for cortar_no in cortar_numbers:
            params = {
                "cortarNo": cortar_no,
                "order": "rank",
                "realEstateType": type_codes,
                "tradeType": deal_codes,
                "priceMin": int(float(condition.get("min_price", 0) or 0)),
                "priceMax": int(float(condition.get("max_price", 0) or 900000000)),
                "rentPriceMin": 0,
                "rentPriceMax": 900000000,
                "areaMin": 0,
                "areaMax": 900000000,
                "showArticle": "false",
                "sameAddressGroup": "true",
                "page": 1,
            }
            urls.append(f"https://new.land.naver.com/api/articles?{urlencode(params)}")
    return urls


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


class RequestLimitReached(Exception):
    pass


class RateLimitDetected(Exception):
    pass


def low_volume_get(session, url, **kwargs):
    request_count = int(getattr(session, "collect_request_count", 0))
    if request_count >= MAX_REQUESTS_PER_RUN:
        raise RequestLimitReached(f"실행당 요청 최대 {MAX_REQUESTS_PER_RUN}회 도달")
    wait_seconds = random.uniform(MIN_RANDOM_DELAY, MAX_RANDOM_DELAY)
    time.sleep(wait_seconds)
    session.collect_request_count = request_count + 1
    return session.get(url, **kwargs)


def fetch(session, url):
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = low_volume_get(session, url, timeout=TIMEOUT)
            if response.status_code == 429:
                raise RateLimitDetected("네이버 요청 제한 감지 (HTTP 429)")
            response.raise_for_status()
            return response.text
        except Exception as error:
            last_error = error
            if isinstance(error, (RateLimitDetected, RequestLimitReached)):
                raise
            if attempt >= MAX_ATTEMPTS:
                break
    raise last_error


def fetch_with_metadata(session, url, log_attempt=None, request_headers=None):
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = low_volume_get(
                session, url, timeout=TIMEOUT, headers=request_headers
            )
            status_code = response.status_code
            response_length = len(response.content or b"")
            if log_attempt:
                log_attempt(status_code, response_length, attempt)
            if status_code == 429:
                raise RateLimitDetected("네이버 요청 제한 감지 (HTTP 429)")
            response.raise_for_status()
            return response.text, status_code, response_length, attempt
        except Exception as error:
            last_error = error
            if log_attempt and getattr(error, "response", None) is None:
                log_attempt("request-error", 0, attempt)
            if isinstance(error, (RateLimitDetected, RequestLimitReached)):
                raise
            if attempt >= MAX_ATTEMPTS:
                break
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


def discover_api_articles(payload):
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    found = []

    def walk(value):
        if isinstance(value, dict):
            article_no = value.get("articleNo") or value.get("articleId")
            if article_no:
                found.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(data.get("articleList", data))
    unique = {}
    for article in found:
        aid = str(article.get("articleNo") or article.get("articleId") or "").strip()
        if aid:
            unique[aid] = article
    return list(unique.values())


def extract_api_row(article, condition):
    aid = str(article.get("articleNo") or article.get("articleId") or "").strip()
    url = f"https://new.land.naver.com/articles/{aid}"
    actual_address = str(
        article.get("roadAddress") or article.get("jibunAddress")
        or article.get("cortarAddress") or article.get("address") or ""
    ).strip()
    address = actual_address or ", ".join(condition.get("regions", []))
    property_type = normalize_type(
        f"{article.get('realEstateTypeName', '')} {article.get('articleName', '')}"
    )
    deal_type = normalize_deal(
        f"{article.get('tradeTypeName', '')} {article.get('dealOrWarrantPrc', '')}"
    )
    area1 = float(article.get("area1", 0) or 0)
    area2 = float(article.get("area2", 0) or 0)
    price = parse_price(article.get("dealOrWarrantPrc", 0))
    rent = parse_price(article.get("rentPrc", 0))
    row = {
        "매물명": str(article.get("articleName") or f"{property_type} 자동수집"),
        "주소": address, "duplicate_address": actual_address,
        "지역": address.split()[0] if address else ", ".join(condition["regions"]),
        "매물종류": property_type, "거래유형": deal_type,
        "매매가(만원)": price if deal_type == "매매" else 0,
        "전세금(만원)": price if deal_type == "전세" else 0,
        "보증금(만원)": price if deal_type == "월세" else 0,
        "월세(만원)": rent, "전용면적(㎡)": area2, "공급면적(㎡)": area1,
        "층수": article.get("floorInfo", ""), "네이버부동산 링크": url,
        "네이버 매물 ID": aid, "naver_url": url, "naver_article_id": aid,
        "auto_collected": "예", "collected_at": now(),
        "source_search_url": condition.get("search_url", ""),
        "collection_condition": json.dumps(condition, ensure_ascii=False, default=str),
        "extraction_status": "네이버 목록 API 자동수집", "extraction_error": "",
        "provider_agency_name": str(article.get("realtorName", "")),
        "agency_name": str(article.get("realtorName", "")),
        "listing_provider": str(article.get("cpName", "")),
        "is_verified_listing": "확인매물" if article.get("verificationTypeCode") else "",
        "verified_date": str(article.get("articleConfirmYmd", "")),
        "listed_date": str(article.get("articleConfirmYmd", "")),
        "platform": "네이버부동산", "first_seen_at": now(), "last_seen_at": now(),
        "매물 상태": "신규",
    }
    return row, url


def extract_html_fallback_row(url, condition):
    aid = article_id(url)
    property_types = condition.get("property_types") or ["기타"]
    deal_types = condition.get("deal_types") or ["매매"]
    property_type = property_types[0] if property_types[0] != "전체" else "기타"
    deal_type = deal_types[0] if deal_types[0] != "전체" else "매매"
    return {
        "매물명": f"{property_type} HTML 자동수집",
        "주소": ", ".join(condition.get("regions", [])),
        "지역": ", ".join(condition.get("regions", [])),
        "매물종류": property_type, "거래유형": deal_type,
        "네이버부동산 링크": url, "네이버 매물 ID": aid,
        "naver_url": url, "naver_article_id": aid, "auto_collected": "예",
        "collected_at": now(), "source_search_url": condition.get("search_url", ""),
        "collection_condition": json.dumps(condition, ensure_ascii=False, default=str),
        "extraction_status": "HTML 목록 자동수집", "extraction_error": "",
        "platform": "네이버부동산", "first_seen_at": now(), "last_seen_at": now(),
        "매물 상태": "신규",
    }


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


def emit_log(condition, status, message="", url=""):
    print(f"{status}: {message}")
    append_log(condition, status, message, url)


def header_summary():
    return (
        f"User-Agent={HEADERS['User-Agent']}; Referer={HEADERS['Referer']}; "
        f"Accept-Language={HEADERS['Accept-Language']}"
    )


def friendly_error(error, fallback="자동 추출 실패"):
    if isinstance(error, RateLimitDetected):
        return "네이버 요청 제한 감지 (HTTP 429)"
    if isinstance(error, RequestLimitReached):
        return str(error)
    if isinstance(error, (requests.Timeout, requests.ConnectionError)):
        return "네이버 서버 응답 지연"
    return f"{fallback}: {type(error).__name__}: {error}"


def duplicate_keys(rows):
    keys = set()
    for row in rows:
        aid = row.get("naver_article_id") or row.get("네이버 매물 ID", "")
        url = row.get("naver_url") or row.get("네이버부동산 링크", "")
        address = row.get("duplicate_address", row.get("주소", ""))
        parts = [
            str(address).strip(), str(row.get("매매가(만원)", "")).strip(),
            str(row.get("전용면적(㎡)", "")).strip(),
        ]
        if not parts[0]:
            parts = []
        combo = "|".join(parts) if any(parts) else ""
        keys.update(item for item in [
            f"id:{aid}" if aid else "", f"url:{url}" if url else "",
            f"combo:{combo}" if combo else "",
        ] if item)
    return keys


def main():
    emit_log({}, "실행 시간", now())
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
    active_conditions = sorted(
        [item for item in conditions if item.get("enabled", True)],
        key=lambda item: item.get("last_collected_at", ""),
    )[:1]
    emit_log({}, "Loaded conditions", f"{len(conditions)} total, {len(active_conditions)} active")
    if not active_conditions:
        emit_log({}, "Collection complete", "0 new listing(s): no active conditions")
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
    total_collected = 0
    duplicate_count = 0
    filtered_count = 0
    failed_count = 0
    with requests.Session() as session:
        session.collect_request_count = 0
        session.headers.update(HEADERS)
        emit_log({}, "Request headers", header_summary())
        for condition in active_conditions:
            if len(new_rows) >= MAX_NEW:
                break
            condition["last_collected_at"] = now()
            emit_log(
                condition, "처리한 조건",
                json.dumps({
                    "regions": condition.get("regions", []),
                    "property_types": condition.get("property_types", []),
                    "deal_types": condition.get("deal_types", []),
                    "min_price": condition.get("min_price", 0),
                    "max_price": condition.get("max_price", 0),
                }, ensure_ascii=False),
            )
            configured_url = str(condition.get("search_url", "")).strip()
            targets = []
            if configured_url and "new.land.naver.com/search?keyword=" not in configured_url:
                targets.append(configured_url)
            targets.extend(build_naver_api_urls(condition))
            targets = list(dict.fromkeys(targets))[:1]
            condition["search_url"] = configured_url or (targets[0] if targets else build_search_url(condition))
            candidates = []
            for search_url in targets:
                if len(new_rows) >= MAX_NEW:
                    break
                emit_log(condition, "Generated search URL", search_url, search_url)
                try:
                    def log_attempt(status_code, response_length, retry_count):
                        emit_log(condition, "Status Code", str(status_code), search_url)
                        emit_log(condition, "Retry Count", str(retry_count), search_url)
                        emit_log(condition, "Raw response length", str(response_length), search_url)

                    search_payload, status_code, response_length, retry_count = fetch_with_metadata(
                        session, search_url, log_attempt=log_attempt
                    )
                    api_articles = discover_api_articles(search_payload)
                    if api_articles:
                        candidates.extend(("api", article) for article in api_articles[:MAX_CANDIDATES])
                    else:
                        candidates.extend(("url", url) for url in discover_urls(search_payload)[:MAX_CANDIDATES])
                    emit_log(condition, "Final Result", f"API request success after {retry_count} attempt(s)")
                except Exception as error:
                    failed_count += 1
                    emit_log(condition, "Error reason if failed", friendly_error(error), search_url)
                    if isinstance(error, RateLimitDetected):
                        emit_log(
                            condition, "네이버 요청 제한 감지",
                            "HTTP 429 감지. 추가 요청 없이 다음 실행까지 대기합니다.", search_url,
                        )
                        emit_log(condition, "Final Result", "Stopped safely after HTTP 429", search_url)
                        break
                    html_url = build_search_url(condition)
                    emit_log(condition, "HTML fallback URL", html_url, html_url)
                    try:
                        html_headers = {
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                        }
                        html_payload, html_status, html_length, html_retry = fetch_with_metadata(
                            session,
                            html_url,
                            log_attempt=lambda status, length, retry: (
                                emit_log(condition, "Status Code", str(status), html_url),
                                emit_log(condition, "Retry Count", str(retry), html_url),
                                emit_log(condition, "Raw response length", str(length), html_url),
                            ),
                            request_headers=html_headers,
                        )
                        html_urls = discover_urls(html_payload)[:MAX_CANDIDATES]
                        candidates.extend(("url", url) for url in html_urls)
                        emit_log(
                            condition, "Final Result",
                            f"HTML fallback success after {html_retry} attempt(s)", html_url,
                        )
                    except Exception as html_error:
                        failed_count += 1
                        if isinstance(html_error, RateLimitDetected):
                            emit_log(
                                condition, "네이버 요청 제한 감지",
                                "HTML 요청에서 HTTP 429 감지. 다음 실행까지 대기합니다.", html_url,
                            )
                        emit_log(
                            condition, "Final Result",
                            f"API and HTML fallback failed: {friendly_error(html_error)}", html_url,
                        )
                if len(candidates) >= MAX_CANDIDATES:
                    break
            unique_candidates = {}
            for kind, value in candidates:
                aid = str(value.get("articleNo") or value.get("articleId")) if kind == "api" else article_id(value)
                key = aid or str(value)
                unique_candidates[key] = (kind, value)
            candidates = list(unique_candidates.values())
            total_collected += len(candidates)
            emit_log(condition, "Parsed Listing Count", str(len(candidates)))
            emit_log(condition, "Found listings count", str(len(candidates)))
            if not candidates:
                emit_log(
                    condition, "No new listings",
                    "검색 응답에서 매물 목록을 찾지 못했습니다. 검색 조건 또는 네이버 응답을 확인하세요.",
                    condition["search_url"],
                )
                continue
            for kind, candidate in candidates:
                if len(new_rows) >= MAX_NEW:
                    break
                if kind == "api":
                    row, url = extract_api_row(candidate, condition)
                else:
                    url = candidate
                    row = extract_html_fallback_row(url, condition)
                aid = article_id(url)
                if f"id:{aid}" in known or f"url:{url}" in known:
                    duplicate_count += 1
                    emit_log(condition, "Duplicate skipped", "매물 ID 또는 URL 중복", url)
                    for existing in rows:
                        existing_id = existing.get("naver_article_id") or existing.get("네이버 매물 ID", "")
                        existing_url = existing.get("naver_url") or existing.get("네이버부동산 링크", "")
                        if (aid and existing_id == aid) or existing_url == url:
                            existing["last_seen_at"] = now()
                            updated_existing = True
                            break
                    continue
                try:
                    duplicate_address = row.get("duplicate_address", row.get("주소", ""))
                    combo_parts = [
                        str(duplicate_address).strip(),
                        str(row.get("매매가(만원)", "")).strip(),
                        str(row.get("전용면적(㎡)", "")).strip(),
                    ]
                    if not combo_parts[0]:
                        combo_parts = []
                    combo = "combo:" + "|".join(combo_parts) if any(combo_parts) else ""
                    if combo and combo in known:
                        duplicate_count += 1
                        emit_log(condition, "Duplicate skipped", "주소 + 가격 + 면적 중복", url)
                        continue
                    if not matches_condition(row, condition):
                        filtered_count += 1
                        continue
                    new_rows.append(row)
                    condition["new_listing_count"] += 1
                    known.update(item for item in [f"id:{article_id(url)}", f"url:{url}", combo] if item)
                    emit_log(condition, "New listing", "저장 대상에 추가", url)
                except Exception as error:
                    failed_count += 1
                    emit_log(condition, "Extraction failed", friendly_error(error), url)
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
    emit_log({}, "New listings saved count", str(len(new_rows)))
    emit_log({}, "Duplicate skipped count", str(duplicate_count))
    if not new_rows:
        if total_collected == 0:
            reason = "검색 결과 후보 매물이 없습니다."
        elif duplicate_count == total_collected:
            reason = "수집된 매물이 모두 중복입니다."
        elif filtered_count:
            reason = f"조건 불일치 {filtered_count}개, 중복 {duplicate_count}개, 추출 실패 {failed_count}개"
        else:
            reason = f"중복 {duplicate_count}개, 추출 실패 {failed_count}개"
        emit_log({}, "No new listings", reason)
    emit_log(
        {}, "Collection complete",
        f"Found listings count={total_collected}, New listings saved count={len(new_rows)}, "
        f"Duplicate skipped count={duplicate_count}, Filtered={filtered_count}, Failed={failed_count}",
    )


if __name__ == "__main__":
    main()
