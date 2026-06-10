import base64
import hmac
import json
import re
import time
from datetime import datetime
from html import unescape
from pathlib import Path
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen

import pandas as pd
import requests
import streamlit as st

from db_store import (
    DB_FILE,
    init_db,
    load_conditions as db_load_conditions,
    load_listings as db_load_listings,
    load_logs as db_load_logs,
    replace_conditions as db_replace_conditions,
    replace_listings as db_replace_listings,
)


DATA_FILE = Path(__file__).with_name("listings.csv")
CONDITIONS_FILE = Path(__file__).with_name("search_conditions.json")
COLLECT_LOG_FILE = Path(__file__).with_name("collect_logs.csv")
PYEONG = 3.3058
PROPERTY_TYPES = [
    "공장", "창고", "토지", "상가", "원룸", "투룸", "쓰리룸",
    "아파트", "빌라", "오피스텔", "사무실", "분양권", "재개발", "기타",
]
DEAL_TYPES = ["매매", "전세", "월세"]
RESIDENTIAL_TYPES = ["원룸", "투룸", "쓰리룸", "아파트", "빌라", "오피스텔"]
FACTORY_TYPES = ["공장", "창고"]
PROPERTY_STATUSES = ["신규", "검토중", "현장방문", "계약진행", "계약완료", "보류"]
AUTO_PROPERTY_TYPES = [
    "전체", "공장", "창고", "토지", "상가", "원룸", "투룸", "쓰리룸",
    "아파트", "빌라", "오피스텔", "사무실", "기타",
]
AUTO_DEAL_TYPES = ["전체", "매매", "전세", "월세"]
AUTO_REGIONS = [
    "청주시", "충북 전체", "청주시 전체", "청주시 흥덕구", "청주시 상당구", "청주시 서원구",
    "청주시 청원구", "진천군", "음성군", "증평군", "괴산군", "보은군", "옥천군",
    "영동군", "충주시", "제천시", "단양군",
]
INVALID_UI_LISTING_TERMS = [
    "본문 바로가기", "메뉴 접기", "지도 바로가기",
    "단지, 지역, 지하철, 초등학교 검색", "검색", "메뉴", "바로가기",
]

COLUMNS = [
    "매물명", "주소", "지역", "매물종류", "거래유형", "네이버 매물 ID", "네이버부동산 링크",
    "사진 파일명", "사진 데이터", "매매가(만원)", "전세금(만원)", "보증금(만원)", "월세(만원)",
    "관리비(만원)", "권리금(만원)", "대지면적(㎡)", "전용면적(㎡)", "공급면적(㎡)",
    "건축면적(㎡)", "건물면적(㎡)", "대지면적(평)", "전용면적(평)", "공급면적(평)",
    "건물면적(평)", "평당가 기준", "평당가(만원)", "월세 수익률(%)", "전세가율(%)",
    "매매가 대비 보증금 비율(%)", "방 개수", "욕실 수", "층수", "주차 가능 여부",
    "엘리베이터", "옵션", "준공연도", "용도지역", "업종 제한", "유동인구 메모",
    "지목", "도로 접함 여부", "개발 가능성 메모", "진입도로 폭(m)", "전력량(kW)",
    "상수도", "하수도", "호이스트", "폐수 가능 여부", "공장등록 가능 여부",
    "대형차 진입 가능 여부", "층고(m)", "허용 건폐율(%)", "허용 용적률(%)",
    "개발행위 가능 여부", "농지전용 가능 여부", "분할 가능 여부", "관리비 포함 항목",
    "즉시 입주 가능 여부", "현재 임차인 여부", "예상 수익률(%)", "공실 여부",
    "임차인 여부", "계약만료일", "투자 메모", "담당자", "연락처", "현장방문일",
    "매물 상태", "즐겨찾기", "naver_url", "naver_article_id", "auto_collected",
    "collected_at", "source_search_url", "collection_condition", "extraction_status", "extraction_error",
    "agency_name", "agency_owner", "agent_name", "agent_phone", "office_phone",
    "mobile_phone", "agency_address", "agency_registration_number", "platform",
    "provider_agency_name", "listing_provider", "is_verified_listing", "verified_date",
    "listed_date", "updated_date",
    "first_seen_at", "last_seen_at", "ai_summary", "ai_strengths", "ai_risks",
    "ai_investment_points", "ai_location_score", "ai_price_score",
    "ai_access_score", "ai_investment_score", "ai_scarcity_score", "ai_total_score",
    "건폐율(%)", "용적률(%)", "전력당 가격(만원/kW)", "메모",
]

NUMBER_COLUMNS = [
    "매매가(만원)", "전세금(만원)", "보증금(만원)", "월세(만원)", "관리비(만원)", "권리금(만원)",
    "대지면적(㎡)", "전용면적(㎡)", "공급면적(㎡)", "건축면적(㎡)", "건물면적(㎡)",
    "방 개수", "욕실 수", "층수", "준공연도", "진입도로 폭(m)", "전력량(kW)",
    "층고(m)", "허용 건폐율(%)", "허용 용적률(%)", "예상 수익률(%)",
    "ai_location_score", "ai_price_score", "ai_access_score", "ai_investment_score",
    "ai_scarcity_score", "ai_total_score",
]


def get_region(address):
    address = str(address).strip()
    return address.split()[0] if address else "지역 미입력"


def read_csv_file(file):
    last_error = None
    for encoding in ["utf-8-sig", "cp949"]:
        try:
            if hasattr(file, "seek"):
                file.seek(0)
            return pd.read_csv(file, encoding=encoding)
        except UnicodeDecodeError as error:
            last_error = error
    raise last_error


def encode_photo(photo):
    if photo is None:
        return "", ""
    encoded = base64.b64encode(photo.getvalue()).decode("ascii")
    return photo.name, f"data:{photo.type};base64,{encoded}"


def decode_photo(photo_data):
    return base64.b64decode(str(photo_data).split(",", 1)[1])


def parse_price(value):
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").replace(" ", "")
    if not text:
        return 0.0
    total = 0.0
    eok = re.search(r"(\d+(?:\.\d+)?)억", text)
    cheon = re.search(r"(\d+(?:\.\d+)?)천", text)
    baek = re.search(r"(\d+(?:\.\d+)?)백", text)
    manwon = re.search(r"(\d+(?:\.\d+)?)만", text)
    if eok:
        total += float(eok.group(1)) * 10000
    if cheon:
        total += float(cheon.group(1)) * 1000
    if baek:
        total += float(baek.group(1)) * 100
    if manwon:
        total += float(manwon.group(1))
    if total:
        return total
    number = re.search(r"\d+(?:\.\d+)?", text)
    return float(number.group()) if number else 0.0


def collect_json_objects(value, result):
    if isinstance(value, dict):
        result.append(value)
        for child in value.values():
            collect_json_objects(child, result)
    elif isinstance(value, list):
        for child in value:
            collect_json_objects(child, result)


def first_value(objects, keys):
    for obj in objects:
        for key in keys:
            value = obj.get(key)
            if value not in [None, "", [], {}]:
                return value
    return ""


def normalize_property_type(value):
    text = str(value)
    rules = [
        (["공장"], "공장"),
        (["창고"], "창고"),
        (["토지", "대지", "땅"], "토지"),
        (["상가", "점포"], "상가"),
        (["원룸"], "원룸"),
        (["투룸"], "투룸"),
        (["쓰리룸", "3룸"], "쓰리룸"),
        (["아파트"], "아파트"),
        (["빌라", "다세대"], "빌라"),
        (["오피스텔"], "오피스텔"),
        (["사무실", "오피스"], "사무실"),
        (["분양권"], "분양권"),
        (["재개발"], "재개발"),
    ]
    for keywords, property_type in rules:
        if any(keyword in text for keyword in keywords):
            return property_type
    return "기타"


def normalize_deal_type(value):
    text = str(value)
    if re.search(r"매매|매매가|매도가", text):
        return "매매"
    if re.search(r"전세|전세금", text):
        return "전세"
    if re.search(r"월세|보증금(?:\s*/\s*월세)?", text):
        return "월세"
    return "매매"


def extract_naver_article_id(url):
    patterns = [
        r"(?:articleNo=|/articles/)(\d+)",
        r"(?:articleId=|article/)(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, str(url))
        if match:
            return match.group(1)
    return ""


def classify_naver_url(url):
    parsed = urlparse(str(url).strip())
    if parsed.scheme not in ["http", "https"] or not parsed.netloc.endswith("naver.com"):
        return "잘못된 URL"
    return "매물 상세 URL" if extract_naver_article_id(url) else "검색 결과 URL"


def discover_naver_listing_urls(html):
    decoded = unescape(str(html)).replace("\\u002F", "/").replace("\\/", "/")
    urls = []
    seen = set()
    def add_url(candidate):
        clean = candidate.rstrip("\\,}")
        key = listing_url_key(clean)
        if key and key not in seen:
            seen.add(key)
            urls.append(clean)

    for match in re.findall(r"https?://[^\"' <]+", decoded):
        if "new.land.naver.com" in match and extract_naver_article_id(match):
            add_url(match)
    for article_id in re.findall(r"/articles/(\d+)", decoded):
        add_url(f"https://new.land.naver.com/articles/{article_id}")
    for pattern in [r'"articleNo"\s*:\s*"?(\d+)"?', r'"articleId"\s*:\s*"?(\d+)"?']:
        for article_id in re.findall(pattern, decoded):
            add_url(f"https://new.land.naver.com/articles/{article_id}")
    return urls


def listing_url_key(url):
    normalized = str(url).strip().rstrip("/")
    if not normalized:
        return ""
    article_id = extract_naver_article_id(normalized)
    return f"article:{article_id}" if article_id else normalized.lower()


def extract_json_from_html(html):
    objects = []
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.I | re.S)
    for script_text in scripts:
        try:
            collect_json_objects(json.loads(script_text), objects)
        except (json.JSONDecodeError, TypeError):
            continue
    return objects


def parse_area(text, labels):
    for label in labels:
        match = re.search(
            rf"{label}\s*[:：]?\s*([\d,.]+)\s*(㎡|m²|m2|평)",
            text,
            re.I,
        )
        if match:
            area = parse_price(match.group(1))
            return area * PYEONG if match.group(2) == "평" else area
    return 0.0


def extract_named_price(text, labels):
    label_pattern = "|".join(re.escape(label) for label in labels)
    match = re.search(
        rf"(?:{label_pattern})\s*[:：]?\s*"
        rf"(\d+(?:\.\d+)?\s*억(?:\s*\d+(?:\.\d+)?\s*(?:천|백|만))?"
        rf"|\d+(?:\.\d+)?\s*(?:천|백|만)?)(?!\s*/)",
        text,
    )
    return parse_price(match.group(1)) if match else 0


def make_listing_name(address, property_type, deal_type, source_text=""):
    named = re.search(
        r"(?:매물명|제목)\s*[:：]\s*(.{2,80}?)(?=\s+(?:주소|서울특별시|"
        r"부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|울산광역시|"
        r"세종특별자치시|경기도|강원특별자치도|충청북도|충청남도|전북특별자치도|"
        r"전라남도|경상북도|경상남도|제주특별자치도|매매|전세|월세|매매가|"
        r"전세금|보증금|관리비|면적)|[\n|]|$)",
        str(source_text),
    )
    if named:
        return named.group(1).strip()
    parts = [str(address).strip(), property_type, deal_type]
    return " ".join(part for part in parts if part and part != "기타").strip() or "자동 추출 매물"


def extract_labeled_text(text, labels, max_length=100):
    label_pattern = "|".join(re.escape(label) for label in labels)
    match = re.search(
        rf"(?:{label_pattern})\s*[:：]?\s*([^\n|]{{2,{max_length}}}?)"
        rf"(?=\s+(?:중개사무소명|중개사무소 주소|중개사 담당자|중개사 연락처|상호|"
        rf"대표자|담당자|연락처|전화|휴대폰|주소|등록번호|매물명|매매|전세|월세|"
        rf"가격|면적|제공 부동산명|제공 부동산|매물 제공처|제공처|확인매물 여부|"
        rf"확인일|등록일|수정일|업데이트일|네이버부동산|직방|다방)|[\n|]|$)",
        str(text),
    )
    return match.group(1).strip() if match else ""


def normalize_phone(value):
    match = re.search(r"(?<!\d)(0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4})(?!\d)", str(value))
    return re.sub(r"\s+", "-", match.group(1)) if match else ""


def detect_platform(value):
    text = str(value).lower()
    if "naver" in text or "네이버부동산" in text:
        return "네이버부동산"
    if "zigbang" in text or "직방" in text:
        return "직방"
    if "dabang" in text or "다방" in text:
        return "다방"
    return ""


def extract_agency_info(text, objects=None, source_url=""):
    objects = objects or []
    office_phone = normalize_phone(first_value(objects, ["officePhone", "telephone", "officeTel"]))
    mobile_phone = normalize_phone(first_value(objects, ["mobilePhone", "cellPhone", "mobileTel"]))
    general_phone = normalize_phone(first_value(objects, ["phone", "agentPhone", "realtorPhone"]))
    if not office_phone:
        office_phone = normalize_phone(extract_labeled_text(text, ["사무실 전화번호", "대표전화", "전화"]))
    if not mobile_phone:
        mobile_phone = normalize_phone(extract_labeled_text(text, ["휴대폰 번호", "휴대폰", "핸드폰"]))
    if not general_phone:
        general_phone = normalize_phone(extract_labeled_text(text, ["중개사 연락처", "담당자 연락처", "연락처"]))
    return {
        "agency_name": str(first_value(objects, ["realtorName", "agencyName", "brokerageName"])).strip()
        or extract_labeled_text(text, ["중개사무소명", "중개사무소", "부동산명", "상호"]),
        "agency_owner": str(first_value(objects, ["representativeName", "ownerName"])).strip()
        or extract_labeled_text(text, ["대표자명", "대표자"]),
        "agent_name": str(first_value(objects, ["agentName", "managerName", "realtorManagerName"])).strip()
        or extract_labeled_text(text, ["매물 담당자명", "중개사 담당자", "중개사명", "담당자"]),
        "agent_phone": general_phone,
        "office_phone": office_phone,
        "mobile_phone": mobile_phone,
        "agency_address": str(first_value(objects, ["realtorAddress", "agencyAddress"])).strip()
        or extract_labeled_text(text, ["중개사무소 주소", "사무실 주소"]),
        "agency_registration_number": str(
            first_value(objects, ["registrationNumber", "realtorRegistrationNumber"])
        ).strip() or extract_labeled_text(text, ["중개사무소 등록번호", "등록번호"]),
        "platform": detect_platform(f"{source_url} {text}"),
    }


def normalize_listing_date(value):
    text = str(value).strip()
    match = re.search(r"\b(\d{2,4}[./-]\d{1,2}[./-]\d{1,2})\b", text)
    return match.group(1) if match else ""


def extract_source_info(text, objects=None):
    objects = objects or []
    verified_text = str(first_value(
        objects, ["verifiedListing", "isVerified", "verificationType", "verificationName"]
    ))
    if not verified_text:
        verified_text = extract_labeled_text(text, ["확인매물 여부", "확인 여부"])
    is_verified = ""
    if re.search(r"확인매물|확인 매물|true|Y", f"{verified_text} {text}", re.I):
        is_verified = "확인매물"
    elif re.search(r"미확인매물|미확인 매물|false|N", verified_text, re.I):
        is_verified = "미확인"

    provider = str(first_value(
        objects, ["providerName", "sourceName", "listingProvider", "articleProviderName"]
    )).strip() or extract_labeled_text(text, ["매물 제공처", "제공처"])
    if not provider:
        provider_match = re.search(
            r"((?:네이버부동산|부동산써브|직방|다방|한방|부동산114)\s*제공)",
            str(text),
        )
        provider = provider_match.group(1).strip() if provider_match else ""

    return {
        "provider_agency_name": str(first_value(
            objects, ["providerAgencyName", "providerRealtorName", "realtorName", "agencyName"]
        )).strip() or extract_labeled_text(text, ["제공 부동산명", "제공 부동산"]),
        "listing_provider": provider,
        "is_verified_listing": is_verified,
        "verified_date": normalize_listing_date(
            first_value(objects, ["verifiedDate", "verificationDate", "confirmDate"])
        ) or normalize_listing_date(extract_labeled_text(text, ["확인일", "확인매물일"])),
        "listed_date": normalize_listing_date(
            first_value(objects, ["listedDate", "registeredDate", "registrationDate", "createDate"])
        ) or normalize_listing_date(extract_labeled_text(text, ["등록일", "최초 등록일"])),
        "updated_date": normalize_listing_date(
            first_value(objects, ["updatedDate", "modifiedDate", "updateDate", "lastModifiedDate"])
        ) or normalize_listing_date(extract_labeled_text(text, ["수정일", "업데이트일", "최종 수정일"])),
    }


def generate_ai_analysis(row):
    property_type = str(row.get("매물종류", "기타"))
    deal_type = str(row.get("거래유형", "매매"))
    price = row.get("매매가(만원)") or row.get("전세금(만원)") or row.get("보증금(만원)") or 0
    area_name, area = select_price_area(row)
    strengths, risks, points = [], [], []
    if row.get("주차 가능 여부") == "가능":
        strengths.append("주차 가능")
    if row.get("엘리베이터") == "있음":
        strengths.append("엘리베이터 있음")
    if float(row.get("월세 수익률(%)", 0) or 0) >= 5:
        strengths.append(f"예상 월세 수익률 {row['월세 수익률(%)']:.2f}%")
        points.append("현금흐름형 투자 검토 가능")
    if row.get("도로 접함 여부") == "접함" or float(row.get("진입도로 폭(m)", 0) or 0) > 0:
        strengths.append("도로 접근 조건 확인됨")
    if not row.get("주소"):
        risks.append("정확한 주소 확인 필요")
    if not area:
        risks.append("면적 정보 확인 필요")
    if not price:
        risks.append("가격 정보 확인 필요")
    if row.get("공실 여부") == "공실":
        risks.append("현재 공실 상태 확인 필요")
    if not points:
        points.append("현장 확인 후 가격과 입지 경쟁력 비교 필요")
    strengths = strengths[:5] or ["입력된 정보 기준 추가 장점 확인 필요"]
    risks = risks[:5] or ["등기·권리관계 및 현장 상태 확인 필요"]

    location = 55 + (10 if row.get("주소") else 0)
    price_score = 55 + (10 if price and area else 0)
    access = 50 + (15 if row.get("주차 가능 여부") == "가능" else 0)
    access += 10 if row.get("도로 접함 여부") == "접함" or float(row.get("진입도로 폭(m)", 0) or 0) > 0 else 0
    investment = 50 + min(int(float(row.get("월세 수익률(%)", 0) or 0) * 5), 30)
    scarcity = 55 + (10 if property_type in ["공장", "토지", "상가"] else 0)
    scores = [min(location, 100), min(price_score, 100), min(access, 100), min(investment, 100), min(scarcity, 100)]
    summary = (
        f"■ 핵심 정보\n- 매물종류: {property_type}\n- 거래유형: {deal_type}\n"
        f"- 가격: {float(price):,.0f}만원\n- 면적: {area_name} {area:.2f}평\n\n"
        f"■ 장점\n" + "\n".join(f"- {item}" for item in strengths) + "\n\n"
        f"■ 단점/체크사항\n" + "\n".join(f"- {item}" for item in risks) + "\n\n"
        f"■ 투자 포인트\n" + "\n".join(f"- {item}" for item in points) + "\n\n"
        f"■ 한줄평\n- 입력된 정보 기준으로 현장 확인과 가격 비교가 필요한 {property_type} 매물"
    )
    return {
        "ai_summary": summary, "ai_strengths": "\n".join(strengths),
        "ai_risks": "\n".join(risks), "ai_investment_points": "\n".join(points),
        "ai_location_score": scores[0], "ai_price_score": scores[1],
        "ai_access_score": scores[2], "ai_investment_score": scores[3],
        "ai_scarcity_score": scores[4], "ai_total_score": round(sum(scores) / len(scores)),
    }


def parse_listing_text(text):
    clean = re.sub(r"\s+", " ", str(text)).strip()
    if not clean:
        return None

    address_match = re.search(
        r"((?:서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|"
        r"대전광역시|울산광역시|세종특별자치시|경기도|강원특별자치도|"
        r"충청북도|충청남도|전북특별자치도|전라남도|경상북도|경상남도|"
        r"제주특별자치도)\s+[가-힣0-9\s\-로길동읍면리]+)",
        clean,
    )
    address = address_match.group(1).strip() if address_match else ""
    if address:
        address = re.split(
            r"\s+(?:공장|창고|토지|상가|원룸|투룸|쓰리룸|아파트|빌라|"
            r"오피스텔|사무실|매매|전세|월세|매매가|보증금|관리비|"
            r"대지면적|전용면적|공급면적|건물면적|층수)\b",
            address,
            maxsplit=1,
        )[0].strip()
    property_type = normalize_property_type(clean)
    deal_type = normalize_deal_type(clean)

    sale_price = extract_named_price(clean, ["매매가", "매도가", "매매"])
    jeonse_price = extract_named_price(clean, ["전세금", "전세가", "전세"])
    deposit = extract_named_price(clean, ["보증금"])
    rent = extract_named_price(clean, ["월세"])
    combined_rent = re.search(
        r"(?:보증금\s*[:：]?\s*)?([\d,.억천백만\s]+)\s*/\s*"
        r"(?:월세\s*[:：]?\s*)?([\d,.억천백만\s]+)",
        clean,
    )
    floor_match = re.search(r"(?:해당층|층수|현재층)\s*[:：]?\s*(\d+)", clean)
    if not floor_match:
        floor_match = re.search(r"(?<!\d)(\d+)\s*층", clean)
    room_match = re.search(r"(?:방\s*(?:개수|수)?|방수)\s*[:：]?\s*(\d+)", clean)
    bath_match = re.search(r"(?:욕실\s*(?:개수|수)?|욕실수)\s*[:：]?\s*(\d+)", clean)

    if combined_rent:
        deposit = parse_price(combined_rent.group(1))
        rent = parse_price(combined_rent.group(2))

    exclusive_area = parse_area(clean, ["전용면적", "전용"])
    supply_area = parse_area(clean, ["공급면적", "공급"])
    land_area = parse_area(clean, ["대지면적", "토지면적", "대지"])
    building_area = parse_area(clean, ["건물면적", "연면적"])
    if not any([exclusive_area, supply_area, land_area, building_area]):
        generic_area = re.search(
            r"(?<![가-힣])면적\s*[:：]?\s*([\d,.]+)\s*(㎡|m²|m2|평)", clean, re.I
        )
        if generic_area:
            exclusive_area = parse_price(generic_area.group(1))
            if generic_area.group(2) == "평":
                exclusive_area *= PYEONG

    result = {
        "매물명": make_listing_name(address, property_type, deal_type, text),
        "주소": address,
        "매물종류": property_type,
        "거래유형": deal_type,
        "매매가(만원)": sale_price,
        "전세금(만원)": jeonse_price,
        "보증금(만원)": deposit,
        "월세(만원)": rent,
        "관리비(만원)": parse_price(
            re.search(r"관리비\s*[:：]?\s*([0-9,.억만\s]+)", clean).group(1)
        ) if re.search(r"관리비\s*[:：]?\s*([0-9,.억만\s]+)", clean) else 0,
        "전용면적(㎡)": exclusive_area,
        "공급면적(㎡)": supply_area,
        "대지면적(㎡)": land_area,
        "건물면적(㎡)": building_area,
        "층수": int(floor_match.group(1)) if floor_match else 0,
        "방 개수": int(room_match.group(1)) if room_match else 0,
        "욕실 수": int(bath_match.group(1)) if bath_match else 0,
        "주차 가능 여부": "불가"
        if re.search(r"주차\s*(?:불가|없음|X)", clean, re.I)
        else "가능"
        if re.search(r"주차\s*(?:가능|O|있음)", clean, re.I)
        else "미확인",
        "엘리베이터": "없음"
        if re.search(r"(?:엘리베이터|승강기)\s*(?:없음|X|무)", clean, re.I)
        else "있음"
        if re.search(r"(?:엘리베이터|승강기)\s*(?:있음|O|유)", clean, re.I)
        else "미확인",
    }
    result.update(extract_agency_info(text))
    result.update(extract_source_info(text))
    observed_at = datetime.now().isoformat(timespec="seconds")
    result["first_seen_at"] = observed_at
    result["last_seen_at"] = observed_at
    meaningful = sum(bool(value) for key, value in result.items() if key not in ["매물종류", "거래유형"])
    return result if meaningful else None


def parse_manual_paste(url="", description="", agency_text="", verification_text=""):
    combined_text = "\n".join(
        value.strip()
        for value in [description, agency_text, verification_text]
        if str(value).strip()
    )
    result = parse_listing_text(combined_text) or {}
    clean_url = str(url).strip()
    if clean_url:
        result["네이버부동산 링크"] = clean_url
        result["naver_url"] = clean_url
        article_id = extract_naver_article_id(clean_url)
        result["네이버 매물 ID"] = article_id
        result["naver_article_id"] = article_id
        result["platform"] = result.get("platform") or detect_platform(clean_url)
    return result or None


def build_listing_result(objects, page_text):
    address = first_value(objects, ["roadAddress", "jibunAddress", "address", "location"])
    property_text = first_value(
        objects, ["realEstateTypeName", "articleName", "buildingTypeName"]
    )
    deal_type = normalize_deal_type(
        f"{first_value(objects, ['tradeTypeName', 'tradeType'])} {page_text}"
    )
    sale_price = parse_price(first_value(objects, ["dealPrice", "price"]))
    warrant_price = parse_price(
        first_value(objects, ["dealOrWarrantPrc", "warrantPrice", "deposit", "depositPrice"])
    )
    result = {
        "주소": str(address),
        "매물종류": normalize_property_type(f"{property_text} {page_text}"),
        "거래유형": deal_type,
        "매매가(만원)": sale_price or (warrant_price if deal_type == "매매" else 0),
        "전세금(만원)": warrant_price if deal_type == "전세" else 0,
        "보증금(만원)": warrant_price if deal_type == "월세" else 0,
        "월세(만원)": parse_price(first_value(objects, ["rentPrc", "rentPrice", "monthlyRent"])),
        "관리비(만원)": parse_price(first_value(objects, ["maintenanceFee", "manageCost"])),
        "전용면적(㎡)": parse_price(first_value(objects, ["area2", "exclusiveArea"])),
        "공급면적(㎡)": parse_price(first_value(objects, ["area1", "supplyArea"])),
        "대지면적(㎡)": parse_price(first_value(objects, ["landArea"])),
        "건물면적(㎡)": parse_price(first_value(objects, ["buildingArea", "totalArea"])),
        "층수": parse_price(first_value(objects, ["floorInfo", "floor", "correspondingFloorCount"])),
        "방 개수": parse_price(first_value(objects, ["roomCount", "roomCnt"])),
        "욕실 수": parse_price(first_value(objects, ["bathroomCount", "bathroomCnt"])),
        "주차 가능 여부": "가능"
        if str(first_value(objects, ["parkingPossibleYN", "parkingCount"])).upper() not in ["", "N", "0"]
        else "미확인",
        "엘리베이터": "있음"
        if str(first_value(objects, ["elevatorYN", "elevatorCount"])).upper() not in ["", "N", "0"]
        else "미확인",
    }
    if not address:
        address_match = re.search(r"([가-힣]+(?:시|도)\s+[가-힣]+(?:시|군|구)[^|]{0,50})", page_text)
        if address_match:
            result["주소"] = address_match.group(1).strip()
    text_result = parse_listing_text(page_text)
    if text_result:
        for key, value in text_result.items():
            if result.get(key) in [None, "", 0, 0.0, "기타", "미확인"] and value not in [
                None, "", 0, 0.0, "기타", "미확인",
            ]:
                result[key] = value
    result["매물명"] = str(
        first_value(objects, ["articleTitle", "title", "articleName"])
    ).strip() or make_listing_name(
        result["주소"], result["매물종류"], result["거래유형"], page_text
    )
    result.update(extract_agency_info(page_text, objects))
    result.update(extract_source_info(page_text, objects))
    meaningful = sum(bool(value) for key, value in result.items() if key not in ["매물종류", "거래유형"])
    return result if meaningful else None


def extract_naver_listing(url):
    logs = []
    parsed = urlparse(url.strip())
    if parsed.scheme not in ["http", "https"] or not parsed.netloc.endswith("naver.com"):
        return None, ["URL 검증 실패: naver.com 주소가 아닙니다."]

    article_id = extract_naver_article_id(url)
    logs.append(f"매물 ID 추출: {article_id or '실패'}")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        ),
        "Referer": "https://new.land.naver.com/",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    }

    with requests.Session() as session:
        session.headers.update(headers)
        for attempt in range(1, 4):
            try:
                logs.append(f"requests 시도 {attempt}/3")
                response = session.get(url, timeout=30)
                logs.append(f"requests 응답: HTTP {response.status_code}, {len(response.text):,}자")
                response.raise_for_status()
                html = response.text
                objects = extract_json_from_html(html)
                logs.append(f"requests JSON 객체 발견: {len(objects):,}개")
                page_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(html))).strip()
                result = build_listing_result(objects, page_text)
                if result:
                    result["platform"] = "네이버부동산"
                    result["first_seen_at"] = datetime.now().isoformat(timespec="seconds")
                    result["last_seen_at"] = result["first_seen_at"]
                    logs.append("requests 단계에서 매물 정보 추출 성공")
                    return result, logs
                logs.append("requests 단계 실패: 초기 HTML에 상세 매물 정보가 없습니다.")
                break
            except requests.exceptions.ReadTimeout:
                logs.append(f"requests 시도 {attempt} 실패: 네이버 서버 응답 지연(ReadTimeout)")
            except Exception as error:
                logs.append(f"requests 시도 {attempt} 실패: {type(error).__name__}: {error}")
            if attempt < 3:
                time.sleep(1)

    try:
        request = Request(url, headers=headers)
        with urlopen(request, timeout=30) as response:
            html = response.read().decode("utf-8", errors="ignore")
        logs.append(f"기본 HTTP 응답: {len(html):,}자")
        objects = extract_json_from_html(html)
        page_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(html))).strip()
        result = build_listing_result(objects, page_text)
        if result:
            result["platform"] = "네이버부동산"
            result["first_seen_at"] = datetime.now().isoformat(timespec="seconds")
            result["last_seen_at"] = result["first_seen_at"]
            logs.append("기본 HTTP 단계에서 매물 정보 추출 성공")
            return result, logs
        logs.append("기본 HTTP 단계 실패: 동적 렌더링 정보가 필요합니다.")
    except Exception as error:
        logs.append(f"기본 HTTP 단계 실패: {type(error).__name__}: {error}")

    logs.append(
        "Playwright/Selenium 검토 결과: Streamlit Cloud에서는 브라우저 설치와 "
        "실행이 불안정하여 기본 기능으로 사용하지 않습니다."
    )
    logs.append("권장 대체 방법: 아래 매물 설명 붙여넣기를 사용하세요.")
    return None, logs


def extract_naver_url(url):
    url_type = classify_naver_url(url)
    if url_type == "잘못된 URL":
        return None, ["URL 검증 실패: naver.com 주소가 아닙니다."], url_type, []
    if url_type == "매물 상세 URL":
        result, logs = extract_naver_listing(url)
        if result:
            result["네이버부동산 링크"] = url.strip()
            result["source_search_url"] = ""
        return result, [f"URL 종류: {url_type}", *logs], url_type, []

    logs = [f"URL 종류: {url_type}", "검색 URL 감지"]
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        ),
        "Referer": "https://new.land.naver.com/",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    }
    candidates = []
    with requests.Session() as session:
        session.headers.update(headers)
        for attempt in range(1, 4):
            try:
                logs.append(f"검색 결과 요청 {attempt}/3")
                response = session.get(url, timeout=30)
                response.raise_for_status()
                candidates = discover_naver_listing_urls(response.text)
                logs.append(f"검색 결과에서 매물 URL {len(candidates):,}개 발견")
                break
            except Exception as error:
                logs.append(f"검색 결과 요청 {attempt} 실패: {type(error).__name__}: {error}")
                if attempt < 3:
                    time.sleep(1)
    if not candidates:
        logs.append("검색 결과 목록 추출 실패: 상세 매물 URL을 찾지 못했습니다.")
        return None, logs, url_type, []

    first_url = candidates[0]
    logs.append(f"첫 번째 매물 자동 추출: {extract_naver_article_id(first_url)}")
    result, detail_logs = extract_naver_listing(first_url)
    logs.extend(detail_logs)
    if result:
        result["네이버부동산 링크"] = first_url
        result["네이버 매물 ID"] = extract_naver_article_id(first_url)
        result["source_search_url"] = url.strip()
    return result, logs, url_type, candidates


def option_index(options, value):
    return options.index(value) if value in options else 0


def select_price_area(row):
    property_type = row["매물종류"]
    if property_type == "토지":
        candidates = [("대지면적", row["대지면적(㎡)"])]
    elif property_type in FACTORY_TYPES:
        candidates = [
            ("건물면적", row["건물면적(㎡)"]),
            ("대지면적", row["대지면적(㎡)"]),
        ]
    else:
        candidates = [
            ("전용면적", row["전용면적(㎡)"]),
            ("건물면적", row["건물면적(㎡)"]),
            ("공급면적", row["공급면적(㎡)"]),
            ("대지면적", row["대지면적(㎡)"]),
        ]
    for name, area in candidates:
        if area > 0:
            return name, area / PYEONG
    return "면적 미입력", 0


def calculate(row):
    sale_price = row["매매가(만원)"]
    jeonse_price = row["전세금(만원)"]
    deposit = row["보증금(만원)"]
    monthly_rent = row["월세(만원)"]
    investment = sale_price - deposit
    area_name, price_pyeong = select_price_area(row)

    result = {
        "대지면적(평)": round(row["대지면적(㎡)"] / PYEONG, 2),
        "전용면적(평)": round(row["전용면적(㎡)"] / PYEONG, 2),
        "공급면적(평)": round(row["공급면적(㎡)"] / PYEONG, 2),
        "건물면적(평)": round(row["건물면적(㎡)"] / PYEONG, 2),
        "평당가 기준": area_name,
        "평당가(만원)": round(sale_price / price_pyeong, 2) if price_pyeong else 0,
        "월세 수익률(%)": round(monthly_rent * 12 / investment * 100, 2)
        if investment > 0
        else 0,
        "예상 수익률(%)": round(monthly_rent * 12 / investment * 100, 2)
        if investment > 0
        else 0,
        "전세가율(%)": round(jeonse_price / sale_price * 100, 2)
        if row["거래유형"] == "전세" and sale_price > 0
        else 0,
        "매매가 대비 보증금 비율(%)": round(deposit / sale_price * 100, 2)
        if sale_price > 0
        else 0,
        "건폐율(%)": round(row["건축면적(㎡)"] / row["대지면적(㎡)"] * 100, 2)
        if row["대지면적(㎡)"] > 0
        else 0,
        "용적률(%)": round(row["건물면적(㎡)"] / row["대지면적(㎡)"] * 100, 2)
        if row["대지면적(㎡)"] > 0
        else 0,
        "전력당 가격(만원/kW)": round(sale_price / row["전력량(kW)"], 2)
        if row["전력량(kW)"] > 0
        else 0,
    }
    return result


def prepare_listings(data):
    data = data.copy()
    rename_map = {"네이버부동산 URL": "네이버부동산 링크"}
    data = data.rename(columns=rename_map)
    for column in COLUMNS:
        if column not in data.columns:
            data[column] = 0 if column in NUMBER_COLUMNS else ""
    data["매물종류"] = data["매물종류"].replace("", "기타").fillna("기타")
    data["거래유형"] = data["거래유형"].replace("", "매매").fillna("매매")
    data["매물 상태"] = data["매물 상태"].replace("", "신규").fillna("신규")
    invalid_ui_rows = data["매물명"].fillna("").astype(str).apply(
        lambda name: any(term in name for term in INVALID_UI_LISTING_TERMS)
    )
    data = data.loc[~invalid_ui_rows].copy()
    data.loc[data["naver_url"].astype(str) == "", "naver_url"] = data["네이버부동산 링크"]
    data.loc[data["naver_article_id"].astype(str) == "", "naver_article_id"] = data["네이버 매물 ID"]
    for column in NUMBER_COLUMNS:
        data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0)
    old_jeonse = (
        (data["거래유형"] == "전세")
        & (data["전세금(만원)"] == 0)
        & (data["보증금(만원)"] > 0)
    )
    data.loc[old_jeonse, "전세금(만원)"] = data.loc[old_jeonse, "보증금(만원)"]

    rows = []
    for _, source in data.iterrows():
        row = source.to_dict()
        row["지역"] = get_region(row["주소"]) if str(row["주소"]).strip() else (
            str(row.get("지역", "")).strip() or "지역 미입력"
        )
        row.update(calculate(row))
        if not row.get("ai_summary"):
            row.update(generate_ai_analysis(row))
        rows.append(row)
    return pd.DataFrame(rows, columns=COLUMNS) if rows else pd.DataFrame(columns=COLUMNS)


def filter_listings(
    data, keyword="", region_keyword="", property_types=None, regions=None,
    deal_types=None, managers=None, statuses=None, favorites_only=False,
    agencies=None, agency_contacts=None,
    min_price=0, max_price=0, min_rent=0, max_rent=0, sort_order="입력 순",
):
    filtered = data.copy()
    property_types = property_types or []
    regions = regions or []
    deal_types = deal_types or []
    managers = managers or []
    statuses = statuses or []
    agencies = agencies or []
    agency_contacts = agency_contacts or []

    if keyword:
        search_columns = [
            "매물명", "주소", "지역", "메모", "옵션", "용도지역", "업종 제한",
            "유동인구 메모", "개발 가능성 메모", "투자 메모", "담당자", "연락처",
            "agency_name", "agency_owner", "agent_name", "agent_phone", "office_phone",
            "mobile_phone", "agency_address", "agency_registration_number", "ai_summary",
        ]
        text = filtered[search_columns].fillna("").astype(str).agg(" ".join, axis=1)
        filtered = filtered[text.str.contains(keyword, case=False, na=False, regex=False)]
    if region_keyword:
        region_text = filtered["주소"].fillna("").astype(str) + " " + filtered["지역"].fillna("").astype(str)
        filtered = filtered[
            region_text.str.contains(region_keyword, case=False, na=False, regex=False)
        ]
    if property_types:
        filtered = filtered[filtered["매물종류"].isin(property_types)]
    if regions:
        filtered = filtered[filtered["지역"].isin(regions)]
    if deal_types:
        filtered = filtered[filtered["거래유형"].isin(deal_types)]
    if managers:
        filtered = filtered[filtered["담당자"].isin(managers)]
    if statuses:
        filtered = filtered[filtered["매물 상태"].isin(statuses)]
    if favorites_only:
        filtered = filtered[filtered["즐겨찾기"].astype(str) == "★"]
    if agencies:
        filtered = filtered[filtered["agency_name"].isin(agencies)]
    if agency_contacts:
        contact_text = (
            filtered["agent_phone"].fillna("").astype(str) + " "
            + filtered["office_phone"].fillna("").astype(str) + " "
            + filtered["mobile_phone"].fillna("").astype(str)
        )
        filtered = filtered[contact_text.apply(lambda value: any(item in value for item in agency_contacts))]

    filtered = filtered[filtered["매매가(만원)"] >= min_price]
    filtered = filtered[filtered["월세(만원)"] >= min_rent]
    if max_price > 0:
        filtered = filtered[filtered["매매가(만원)"] <= max_price]
    if max_rent > 0:
        filtered = filtered[filtered["월세(만원)"] <= max_rent]

    sort_map = {
        "수익률 높은 순": ("월세 수익률(%)", False),
        "평당가 낮은 순": ("평당가(만원)", True),
        "매매가 낮은 순": ("매매가(만원)", True),
        "매매가 높은 순": ("매매가(만원)", False),
    }
    if sort_order in sort_map:
        column, ascending = sort_map[sort_order]
        filtered = filtered.sort_values(column, ascending=ascending)
    return filtered


def load_listings():
    try:
        init_db()
        rows = db_load_listings()
        if rows:
            return prepare_listings(pd.DataFrame(rows))
        if DATA_FILE.exists():
            data = prepare_listings(read_csv_file(DATA_FILE))
            if not data.empty:
                db_replace_listings(data.to_dict("records"))
            return data
        return pd.DataFrame(columns=COLUMNS)
    except Exception as error:
        st.warning(f"저장된 매물을 읽지 못했습니다: {error}")
        return pd.DataFrame(columns=COLUMNS)


def save_listings(data):
    prepared = prepare_listings(data)
    db_replace_listings(prepared.to_dict("records"))
    prepared.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")


def load_conditions():
    try:
        init_db()
        conditions = db_load_conditions()
        if CONDITIONS_FILE.exists():
            try:
                conditions = json.loads(CONDITIONS_FILE.read_text(encoding="utf-8"))
                db_replace_conditions(conditions)
            except (json.JSONDecodeError, OSError):
                pass
        return [normalize_condition(item) for item in conditions]
    except (json.JSONDecodeError, OSError, ValueError):
        return []


def save_conditions(conditions):
    conditions = [normalize_condition(item) for item in conditions]
    try:
        db_replace_conditions(conditions)
    except Exception as error:
        return False, f"조건 저장 실패: {error}"
    try:
        CONDITIONS_FILE.write_text(
            json.dumps(conditions, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as error:
        return False, f"조건 저장 실패: {error}"
    return sync_conditions_to_github()


def github_condition_settings():
    try:
        token = str(st.secrets.get("GITHUB_TOKEN", "")).strip()
        repository = str(st.secrets.get("GITHUB_REPOSITORY", "Sugoil/factory-manager")).strip()
        branch = str(st.secrets.get("GITHUB_BRANCH", "main")).strip()
        return token, repository, branch
    except Exception:
        return "", "", "main"


def save_github_api_logs(logs):
    try:
        st.session_state.github_api_logs = logs
    except Exception:
        pass


def github_api_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def github_response_error(response):
    try:
        message = str(response.json().get("message", "")).strip()
    except Exception:
        message = ""
    status = getattr(response, "status_code", "")
    return f"HTTP {status}{f' - {message}' if message else ''}"


def test_github_connection():
    token, repository, branch = github_condition_settings()
    logs = [
        f"GITHUB_TOKEN 인식: {'성공' if token else '실패'}",
        f"GITHUB_REPOSITORY 인식: {repository or '실패'}",
        f"GITHUB_BRANCH 인식: {branch or '실패'}",
    ]
    if not token or not repository or not branch:
        save_github_api_logs(logs)
        return False, "GitHub Secrets 설정을 확인해주세요.", "", "", "", {}

    headers = github_api_headers(token)
    try:
        repository_response = requests.get(
            f"https://api.github.com/repos/{repository}", headers=headers, timeout=20
        )
        if repository_response.status_code != 200:
            logs.append(f"저장소 연결: 실패 ({github_response_error(repository_response)})")
            save_github_api_logs(logs)
            return False, "GitHub 저장소 연결에 실패했습니다.", "", "", "", {}
        logs.append("저장소 연결: 성공")

        branch_response = requests.get(
            f"https://api.github.com/repos/{repository}/branches/{quote_plus(branch)}",
            headers=headers,
            timeout=20,
        )
        if branch_response.status_code != 200:
            logs.append(f"브랜치 확인: 실패 ({github_response_error(branch_response)})")
            save_github_api_logs(logs)
            return False, "GitHub 브랜치 확인에 실패했습니다.", "", "", "", {}
        logs.append(f"브랜치 확인: 성공 ({branch})")
        save_github_api_logs(logs)
        return True, "", token, repository, branch, headers
    except requests.Timeout:
        logs.append("GitHub 연결: 실패 (서버 응답 지연)")
        save_github_api_logs(logs)
        return False, "GitHub 서버 응답이 지연되었습니다.", "", "", "", {}
    except requests.RequestException as error:
        status = getattr(getattr(error, "response", None), "status_code", "")
        logs.append(f"GitHub 연결: 실패{f' (HTTP {status})' if status else ''}")
        save_github_api_logs(logs)
        return False, "GitHub API 연결에 실패했습니다.", "", "", "", {}


def sync_file_to_github(path, commit_message):
    connected, error, token, repository, branch, headers = test_github_connection()
    logs = list(st.session_state.get("github_api_logs", []))
    if not connected:
        return False, error
    api_url = f"https://api.github.com/repos/{repository}/contents/{path.name}"
    try:
        current = requests.get(api_url, headers=headers, params={"ref": branch}, timeout=20)
        if current.status_code == 200:
            sha = current.json().get("sha", "")
            logs.append(f"{path.name} 확인: 기존 파일 수정")
        elif current.status_code == 404:
            sha = ""
            logs.append(f"{path.name} 확인: 새 파일 생성")
        else:
            logs.append(f"{path.name} 확인: 실패 ({github_response_error(current)})")
            save_github_api_logs(logs)
            return False, f"GitHub 파일 확인 실패: {github_response_error(current)}"
        payload = {
            "message": commit_message,
            "content": base64.b64encode(path.read_bytes()).decode("ascii"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha
        response = requests.put(api_url, headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        logs.append(f"{path.name} 저장: 성공 ({'수정' if sha else '생성'})")
        save_github_api_logs(logs)
        return True, ""
    except requests.Timeout:
        logs.append(f"{path.name} 저장: 실패 (서버 응답 지연)")
        save_github_api_logs(logs)
        return False, "GitHub 서버 응답이 지연되었습니다."
    except requests.RequestException as error:
        status = getattr(getattr(error, "response", None), "status_code", "")
        logs.append(f"{path.name} 저장: 실패{f' (HTTP {status})' if status else ''}")
        save_github_api_logs(logs)
        return False, f"GitHub API 저장 실패{f' (HTTP {status})' if status else ''}"
    except OSError as error:
        logs.append(f"{path.name} 저장: 실패 (로컬 파일 읽기 오류)")
        save_github_api_logs(logs)
        return False, f"저장 파일을 읽지 못했습니다: {error}"


def sync_conditions_to_github():
    token, repository, _ = github_condition_settings()
    if not token or not repository:
        return False, "조건 저장 실패: Streamlit Secrets에 GITHUB_TOKEN을 설정해주세요."
    json_synced, error = sync_file_to_github(
        CONDITIONS_FILE, "chore: update auto collect conditions"
    )
    if json_synced:
        return True, "조건 저장 완료"
    return False, f"조건 저장 실패: {error}"


def normalize_condition(condition):
    item = dict(condition)
    regions = item.get("regions") or [item.get("region", "청주시")]
    property_types = item.get("property_types") or [item.get("property_type", "전체")]
    deal_types = item.get("deal_types") or [item.get("deal_type", "전체")]
    item["regions"] = [value for value in regions if value] or ["청주시"]
    item["property_types"] = (
        ["전체"] if "전체" in property_types else [value for value in property_types if value]
    ) or ["전체"]
    item["deal_types"] = (
        ["전체"] if "전체" in deal_types else [value for value in deal_types if value]
    ) or ["전체"]
    item["enabled"] = bool(item.get("enabled", True))
    item["search_url"] = str(item.get("search_url", "")).strip()
    item["registered_at"] = item.get("registered_at") or datetime.now().isoformat(timespec="seconds")
    item["last_collected_at"] = item.get("last_collected_at", "")
    item["new_listing_count"] = int(item.get("new_listing_count", 0) or 0)
    return item


def build_condition_search_url(regions, property_types, deal_types):
    keywords = []
    keywords.extend([] if "전체" in regions else regions)
    keywords.extend([] if "전체" in property_types else property_types)
    keywords.extend([] if "전체" in deal_types else deal_types)
    keyword = " ".join(keywords) or "충북 부동산"
    return f"https://new.land.naver.com/search?keyword={quote_plus(keyword)}"


def get_app_password():
    try:
        return str(st.secrets["APP_PASSWORD"])
    except Exception:
        return ""


def show_login():
    st.title("전체 부동산 매물 관리")
    with st.form("login_form"):
        password = st.text_input("비밀번호", type="password", key="login_password")
        submitted = st.form_submit_button("로그인", use_container_width=True, key="login_submit")
    if submitted:
        app_password = get_app_password()
        if not app_password:
            st.error("앱 비밀번호가 설정되지 않았습니다.")
        elif hmac.compare_digest(password, app_password):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다")


def show_table(data, key):
    st.write(f"표시 매물 **{len(data):,}개**")
    table = data.drop(columns=["사진 데이터"], errors="ignore")
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "네이버부동산 링크": st.column_config.LinkColumn(
                "네이버부동산", display_text="매물 열기"
            ),
            "평당가(만원)": st.column_config.NumberColumn(format="%,.2f"),
            "월세 수익률(%)": st.column_config.NumberColumn(format="%.2f%%"),
            "예상 수익률(%)": st.column_config.NumberColumn(format="%.2f%%"),
            "전세가율(%)": st.column_config.NumberColumn(format="%.2f%%"),
            "매매가 대비 보증금 비율(%)": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )
    csv_data = data.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "현재 목록 CSV 다운로드", csv_data, f"부동산_매물목록_{key}.csv",
        "text/csv", key=f"download_{key}",
    )
    photos = data[data["사진 데이터"].astype(str).str.startswith("data:image")]
    if not photos.empty:
        options = {
            f"{index + 1}. {row['매물명']}": row["사진 데이터"]
            for index, row in photos.reset_index(drop=True).iterrows()
        }
        selected = st.selectbox(
            "사진 확인", ["선택하지 않음", *options.keys()], key=f"photo_{key}"
        )
        if selected != "선택하지 않음":
            st.image(decode_photo(options[selected]), caption=selected, width=600)


st.set_page_config(page_title="전체 부동산 매물 관리", layout="wide")
st.markdown(
    """
    <style>
    .block-container {padding-top: 1.8rem; max-width: 1550px;}
    [data-testid="stMetric"] {
        background: #f5f7fa; border: 1px solid #e1e6ed;
        padding: 14px; border-radius: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if not st.session_state.get("authenticated", False):
    show_login()
    st.stop()

with st.sidebar:
    st.success("로그인됨")
    st.caption("Cloud에서는 사용 후 CSV를 다운로드해 백업하세요.")
    if st.button("로그아웃", use_container_width=True, key="logout_button"):
        st.session_state.authenticated = False
        st.rerun()

st.title("전체 부동산 매물 관리")
st.caption("주거·상업·토지·공장 매물을 한 곳에서 관리합니다.")
st.success(
    "추천 사용법: 네이버부동산 매물 상세페이지에서 필요한 내용을 복사해 "
    "붙여넣으면 자동으로 정리됩니다."
)

if "listings" not in st.session_state:
    st.session_state.listings = load_listings()

data = st.session_state.listings
total = len(data)
m1, m2, m3, m4 = st.columns(4)
m1.metric("전체 매물", f"{total:,}개")
m2.metric("평균 매매가", f"{data['매매가(만원)'].mean() if total else 0:,.0f}만원")
m3.metric("평균 수익률", f"{data['월세 수익률(%)'].mean() if total else 0:.2f}%")
m4.metric("등록 지역", f"{data['지역'].nunique() if total else 0:,}곳")

with st.expander("CSV 불러오기 / 전체 다운로드"):
    uploaded_csv = st.file_uploader("매물 CSV 불러오기", type="csv", key="csv_upload")
    if uploaded_csv is not None and st.button("CSV 적용", key="csv_apply"):
        try:
            st.session_state.listings = prepare_listings(read_csv_file(uploaded_csv))
            save_listings(st.session_state.listings)
            st.success(f"{len(st.session_state.listings):,}개 매물을 불러왔습니다.")
        except Exception as error:
            st.error(f"CSV를 불러오지 못했습니다: {error}")
    all_csv = st.session_state.listings.to_csv(index=False).encode("utf-8-sig")
    st.download_button("전체 CSV 다운로드", all_csv, "부동산_전체매물.csv", "text/csv", key="csv_download_all")

with st.expander("실험 기능: 자동수집 관심 조건 관리", expanded=False):
    st.warning("네이버부동산은 자동 접근 제한이 있어 현재 자동수집이 불안정합니다.")
    st.info(
        "자동수집은 실험 기능입니다. 기본 사용은 아래 URL/텍스트 붙여넣기를 권장합니다.\n\n"
        "GitHub Actions는 네이버 요청 제한이 발생할 수 있어 로컬 PC 자동수집을 권장합니다.\n\n"
        "네이버 API 방식이 제한될 경우 브라우저 수집 방식으로 실행됩니다.\n\n"
        "최초 1회 Playwright 설치가 필요합니다.\n\n"
        "브라우저 창이 열리면 수집이 끝날 때까지 닫지 마세요.\n\n"
        "`setup_local_scheduler.bat`을 실행하면 3시간마다 자동수집됩니다.\n\n"
        "PC가 꺼져 있으면 자동수집은 실행되지 않습니다."
    )
    conditions = load_conditions()
    if st.session_state.get("condition_notice"):
        notice = st.session_state.pop("condition_notice")
        if notice.startswith("조건 저장 실패") or notice.startswith("GitHub 연결 실패"):
            st.error(notice)
        else:
            st.success(notice)
    if st.button("GitHub 연결 확인", key="github_connection_test"):
        connected, error, _, _, _, _ = test_github_connection()
        if connected:
            st.success("GitHub 연결 성공")
        else:
            st.error(f"GitHub 연결 실패: {error}")
    if st.session_state.get("github_api_logs"):
        with st.expander("GitHub API 저장 로그", expanded=False):
            for github_log in st.session_state.github_api_logs:
                st.write(f"- {github_log}")
    condition_ids = [item["id"] for item in conditions]
    edit_id = st.selectbox(
        "수정할 조건", ["새 조건", *condition_ids], key="condition_edit_id"
    )
    selected_condition = next((item for item in conditions if item["id"] == edit_id), None)
    if st.button("선택 조건 불러오기", key="condition_load") and selected_condition:
        st.session_state.condition_regions = selected_condition["regions"]
        st.session_state.condition_property_types = selected_condition["property_types"]
        st.session_state.condition_deal_types = selected_condition["deal_types"]
        st.session_state.condition_min = float(selected_condition.get("min_price", 0))
        st.session_state.condition_max = float(selected_condition.get("max_price", 0))
        st.session_state.condition_enabled = selected_condition.get("enabled", True)
        st.session_state.condition_url = selected_condition.get("search_url", "")
        st.rerun()

    c1, c2, c3, c4 = st.columns(4)
    condition_regions = c1.multiselect(
        "지역 선택", AUTO_REGIONS, default=["청주시"], key="condition_regions"
    )
    condition_property_types = c2.multiselect(
        "관심 매물종류", AUTO_PROPERTY_TYPES, default=["전체"], key="condition_property_types"
    )
    condition_deal_types = c3.multiselect(
        "관심 거래유형", AUTO_DEAL_TYPES, default=["전체"], key="condition_deal_types"
    )
    condition_enabled = c4.checkbox("자동수집 ON", value=True, key="condition_enabled")
    p1, p2, p3 = st.columns([1, 1, 2])
    condition_min = p1.number_input("최소 가격(만원)", min_value=0.0, step=1000.0, key="condition_min")
    condition_max = p2.number_input("최대 가격(만원)", min_value=0.0, step=1000.0, key="condition_max")
    condition_url = p3.text_input(
        "네이버 관심 검색 URL",
        placeholder="비워두면 선택 조건으로 검색 URL을 자동 구성합니다.",
        key="condition_url",
    )
    effective_url = condition_url.strip() or build_condition_search_url(
        condition_regions, condition_property_types, condition_deal_types
    )
    action_1, action_2, action_3 = st.columns(3)
    if action_1.button("자동수집 조건 추가", key="condition_add"):
        if not condition_regions or not condition_property_types or not condition_deal_types:
            st.error("지역, 매물종류, 거래유형을 각각 하나 이상 선택하세요.")
        else:
            conditions.append({
                "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                "regions": condition_regions, "property_types": condition_property_types,
                "deal_types": condition_deal_types, "min_price": condition_min,
                "max_price": condition_max, "enabled": condition_enabled,
                "search_url": effective_url,
                "registered_at": datetime.now().isoformat(timespec="seconds"),
                "last_collected_at": "",
            })
            synced, notice = save_conditions(conditions)
            st.session_state.condition_notice = notice
            st.rerun()
    if action_2.button("선택 조건 수정", key="condition_update") and selected_condition:
        updated = {
            **selected_condition, "regions": condition_regions,
            "property_types": condition_property_types, "deal_types": condition_deal_types,
            "min_price": condition_min, "max_price": condition_max,
            "enabled": condition_enabled, "search_url": effective_url,
        }
        synced, notice = save_conditions([updated if item["id"] == edit_id else item for item in conditions])
        st.session_state.condition_notice = notice
        st.rerun()
    if action_3.button("선택 조건 ON/OFF 전환", key="condition_toggle") and selected_condition:
        selected_condition["enabled"] = not selected_condition.get("enabled", True)
        synced, notice = save_conditions(conditions)
        st.session_state.condition_notice = notice
        st.rerun()
    if conditions:
        condition_table = pd.DataFrame([
            {
                "지역": ", ".join(item["regions"]),
                "매물종류": ", ".join(item["property_types"]),
                "거래유형": ", ".join(item["deal_types"]),
                "최소 가격": item.get("min_price", 0),
                "최대 가격": item.get("max_price", 0),
                "자동수집": "ON" if item.get("enabled", True) else "OFF",
                "등록일": item.get("registered_at", ""),
                "마지막 수집 시간": item.get("last_collected_at", ""),
                "최근 신규 매물 수": item.get("new_listing_count", 0),
            }
            for item in conditions
        ])
        st.dataframe(
            condition_table.drop(columns=["regions", "property_types", "deal_types"], errors="ignore"),
            use_container_width=True, hide_index=True,
        )
        if st.button("현재 선택 조건 삭제", key="condition_delete") and selected_condition:
            _, notice = save_conditions([item for item in conditions if item["id"] != edit_id])
            st.session_state.condition_notice = notice
            st.rerun()
    db_logs = db_load_logs(limit=100)
    logs = pd.DataFrame(db_logs)
    if logs.empty and COLLECT_LOG_FILE.exists():
        logs = read_csv_file(COLLECT_LOG_FILE).iloc[::-1].reset_index(drop=True)
    enabled_count = sum(1 for item in conditions if item.get("enabled", True))
    status_1, status_2, status_3 = st.columns(3)
    status_1.metric("자동수집 상태", "ON" if enabled_count else "OFF")
    if not logs.empty:
        time_column = "collected_at" if "collected_at" in logs.columns else "수집시간"
        status_column = "status" if "status" in logs.columns else "상태"
        last_time = str(logs.iloc[0].get(time_column, ""))
        successful_count = sum(int(item.get("new_listing_count", 0) or 0) for item in conditions)
        status_2.metric("마지막 수집 시간", last_time or "-")
        status_3.metric("신규 수집 매물 수", f"{successful_count:,}개")
        rate_limited = logs.head(30)[status_column].astype(str).str.contains(
            "네이버 요청 제한 감지", case=False, regex=False
        ).any()
        if rate_limited:
            st.error("네이버 요청 제한 감지: 추가 요청을 중단하고 다음 실행까지 기다립니다.")
        st.markdown("##### 최근 수집 로그")
        st.dataframe(logs.head(30), use_container_width=True, hide_index=True)
        failure_mask = logs[status_column].astype(str).str.contains(
            "실패|failed|No new listings", case=False, regex=True
        )
        failed = logs[failure_mask]
        if not failed.empty:
            st.markdown("##### 수집 실패 로그")
            st.dataframe(failed.head(20), use_container_width=True, hide_index=True)
    else:
        status_2.metric("마지막 수집 시간", "-")
        status_3.metric("신규 수집 매물 수", "0개")
    auto_rows = st.session_state.listings[
        st.session_state.listings["auto_collected"].astype(str) == "예"
    ]
    if not auto_rows.empty:
        st.markdown("##### 자동수집된 신규 매물")
        st.dataframe(
            auto_rows.drop(columns=["사진 데이터"], errors="ignore").tail(20),
            use_container_width=True,
            hide_index=True,
        )

st.subheader("URL/텍스트 붙여넣기 자동정리")
st.info(
    "네이버부동산에서 매물 URL과 화면의 매물 설명을 복사해 붙여넣으세요. "
    "인식된 내용은 아래 입력칸에 채워지며 저장 전에 수정할 수 있습니다."
)
url_1, url_2 = st.columns([4, 1])
with url_1:
    extraction_url = st.text_input(
        "네이버부동산 매물 URL",
        value=st.session_state.get("naver_extract_url", ""),
        placeholder="https://new.land.naver.com/...",
        key="naver_extraction_url",
    )
with url_2:
    st.write("")
    st.write("")
    extract_clicked = st.button("URL 정보 확인 (보조)", use_container_width=True, key="naver_extract_button")

current_url_type = classify_naver_url(extraction_url) if extraction_url.strip() else "URL 미입력"
st.info(f"현재 입력된 URL 종류: **{current_url_type}**")

if extract_clicked:
    try:
        extracted, extraction_logs, detected_url_type, search_candidates = extract_naver_url(extraction_url)
    except Exception as error:
        extracted = None
        extraction_logs = [f"예상하지 못한 실패: {type(error).__name__}: {error}"]
        detected_url_type = classify_naver_url(extraction_url)
        search_candidates = []
    st.session_state.extraction_logs = extraction_logs
    st.session_state.naver_extract_url = extraction_url
    st.session_state.detected_url_type = detected_url_type
    known_url_keys = {
        listing_url_key(value)
        for value in st.session_state.listings["네이버부동산 링크"].fillna("")
        if listing_url_key(value)
    }
    st.session_state.search_result_listings = [
        {
            "순서": index + 1,
            "네이버 매물 ID": extract_naver_article_id(candidate),
            "URL": candidate,
            "신규 여부": "신규" if listing_url_key(candidate) not in known_url_keys else "등록됨",
        }
        for index, candidate in enumerate(search_candidates)
    ]
    if detected_url_type == "검색 결과 URL":
        st.info("검색 URL 감지")
    if extracted:
        st.session_state.extracted_listing = extracted
        st.session_state.naver_extract_url = extracted.get("네이버부동산 링크", extraction_url)
        st.success("가능한 매물 정보를 자동 입력했습니다. 저장 전에 내용을 확인해주세요.")
    else:
        st.session_state.extracted_listing = {}
        if any("ReadTimeout" in log or "응답 지연" in log for log in extraction_logs):
            st.warning("네이버 서버 응답 지연, 나중에 다시 시도하거나 직접 입력해주세요.")
        st.warning("자동 추출 실패, URL은 저장하고 직접 입력하거나 매물 설명을 붙여넣어주세요.")

if st.session_state.get("detected_url_type"):
    st.caption(f"마지막 감지 URL 종류: {st.session_state.detected_url_type}")

search_result_listings = st.session_state.get("search_result_listings", [])
if search_result_listings:
    with st.expander("검색 URL 신규 매물 목록", expanded=True):
        st.write(f"검색 결과 매물 **{len(search_result_listings):,}개**")
        st.dataframe(pd.DataFrame(search_result_listings), use_container_width=True, hide_index=True)

if st.session_state.get("extraction_logs"):
    with st.expander("URL 자동 추출 단계별 로그", expanded=True):
        for log_line in st.session_state.extraction_logs:
            st.write(f"- {log_line}")

with st.expander("매물 정보 붙여넣기 (추천)", expanded=True):
    pasted_description = st.text_area(
        "매물 설명 텍스트",
        placeholder=(
            "예: 경기도 화성시 ... 공장 매매 5억 대지면적 500㎡ "
            "건물면적 300㎡ 층수 2층"
        ),
        height=180,
        key="pasted_listing_description",
    )
    paste_1, paste_2 = st.columns(2)
    agency_pasted_text = paste_1.text_area(
        "중개사무소 정보",
        placeholder="예: 중개사무소명, 담당자, 연락처, 사무실 주소, 등록번호",
        height=130,
        key="pasted_agency_info",
    )
    verification_pasted_text = paste_2.text_area(
        "확인매물/확인일 정보",
        placeholder="예: 확인매물, 확인일 26.06.11, 등록일 26.06.10, 제공 부동산명",
        height=130,
        key="pasted_verification_info",
    )
    parse_text_clicked = st.button("붙여넣은 내용 자동 정리", use_container_width=True, key="parse_pasted_text")

if parse_text_clicked:
    parsed_text = parse_manual_paste(
        extraction_url,
        pasted_description,
        agency_pasted_text,
        verification_pasted_text,
    )
    if parsed_text:
        st.session_state.extracted_listing = parsed_text
        st.session_state.naver_extract_url = extraction_url
        st.session_state.extraction_logs = [
            "붙여넣기 텍스트 읽기 성공",
            "매물·가격·면적·중개사무소·확인매물 정보 중 인식 가능한 항목을 입력했습니다.",
        ]
        st.success("붙여넣은 매물 설명에서 가능한 정보를 자동 입력했습니다.")
        st.rerun()
    else:
        st.session_state.extraction_logs = [
            "붙여넣기 텍스트 읽기 실패: 인식 가능한 주소·가격·면적 정보가 없습니다."
        ]
        st.warning("자동 추출 실패, 붙여넣은 내용을 확인하고 직접 입력해주세요")

auto = st.session_state.get("extracted_listing", {})
selected_type = normalize_property_type(auto.get("매물종류", ""))
st.info(f"자동 판단 매물종류: **{selected_type}**")

with st.form("listing_form", clear_on_submit=True):
    common_1, common_2, common_3 = st.columns(3)
    with common_1:
        st.markdown("#### 기본 정보")
        name = st.text_input("매물명 *", value=str(auto.get("매물명", "")), key="listing_name")
        deal_type = st.selectbox(
            "거래유형", DEAL_TYPES, index=option_index(DEAL_TYPES, auto.get("거래유형", "매매")),
            key="listing_deal_type",
        )
        address = st.text_input("주소", value=str(auto.get("주소", "")), key="listing_address")
        naver_link = st.text_input(
            "네이버부동산 링크",
            value=str(auto.get("네이버부동산 링크", extraction_url)),
            key="listing_naver_link",
        )
        memo = st.text_area("메모", height=100, key="listing_memo")
    with common_2:
        st.markdown("#### 금액")
        sale_price = st.number_input(
            "매매가(만원)", min_value=0.0, value=float(auto.get("매매가(만원)", 0)), step=1000.0,
            key="listing_sale_price",
        )
        jeonse_price = st.number_input(
            "전세금(만원)", min_value=0.0, value=float(auto.get("전세금(만원)", 0)), step=1000.0,
            key="listing_jeonse_price",
        )
        deposit = st.number_input(
            "보증금(만원)", min_value=0.0, value=float(auto.get("보증금(만원)", 0)), step=100.0,
            key="listing_deposit",
        )
        monthly_rent = st.number_input(
            "월세(만원)", min_value=0.0, value=float(auto.get("월세(만원)", 0)), step=10.0,
            key="listing_monthly_rent",
        )
        maintenance_fee = st.number_input(
            "관리비(만원)", min_value=0.0, value=float(auto.get("관리비(만원)", 0)), step=1.0,
            key="listing_maintenance_fee",
        )
        photo = st.file_uploader("매물 사진", type=["jpg", "jpeg", "png", "webp"], key="listing_photo")
    with common_3:
        st.markdown("#### 면적·공통 시설")
        land_area = st.number_input(
            "대지면적(㎡)", min_value=0.0, value=float(auto.get("대지면적(㎡)", 0)), step=1.0,
            key="listing_land_area",
        )
        exclusive_area = st.number_input(
            "전용면적(㎡)", min_value=0.0, value=float(auto.get("전용면적(㎡)", 0)), step=1.0,
            key="listing_exclusive_area",
        )
        supply_area = st.number_input(
            "공급면적(㎡)", min_value=0.0, value=float(auto.get("공급면적(㎡)", 0)), step=1.0,
            key="listing_supply_area",
        )
        building_area = st.number_input(
            "건물면적/연면적(㎡)", min_value=0.0, value=float(auto.get("건물면적(㎡)", 0)), step=1.0,
            key="listing_building_area",
        )
        floor = st.number_input("층수", min_value=0, value=int(auto.get("층수", 0)), step=1, key="listing_floor")

    parking = auto.get("주차 가능 여부", "미확인")
    elevator = auto.get("엘리베이터", "미확인")
    extra = {
        "방 개수": int(auto.get("방 개수", 0)), "욕실 수": int(auto.get("욕실 수", 0)),
        "옵션": "", "준공연도": 0, "권리금(만원)": 0,
        "업종 제한": "", "유동인구 메모": "", "지목": "", "용도지역": "",
        "도로 접함 여부": "", "개발 가능성 메모": "", "건축면적(㎡)": 0,
        "진입도로 폭(m)": 0, "전력량(kW)": 0, "상수도": "", "하수도": "",
        "호이스트": "", "폐수 가능 여부": "", "공장등록 가능 여부": "",
        "대형차 진입 가능 여부": "", "층고(m)": 0, "허용 건폐율(%)": 0,
        "허용 용적률(%)": 0, "개발행위 가능 여부": "", "농지전용 가능 여부": "",
        "분할 가능 여부": "", "관리비 포함 항목": "", "즉시 입주 가능 여부": "",
        "현재 임차인 여부": "",
    }

    st.markdown("#### 매물 상세 정보")
    st.caption(f"{selected_type} 유형에 필요한 상세정보만 표시됩니다.")
    if selected_type in RESIDENTIAL_TYPES:
        c1, c2, c3, c4 = st.columns(4)
        extra["방 개수"] = c1.number_input(
            "방 개수", min_value=0, value=int(auto.get("방 개수", 0)), step=1, key="detail_room_count"
        )
        extra["욕실 수"] = c1.number_input(
            "욕실 개수", min_value=0, value=int(auto.get("욕실 수", 0)), step=1, key="detail_bathroom_count"
        )
        parking_options = ["미확인", "가능", "불가"]
        parking = c2.selectbox(
            "주차 가능 여부", parking_options,
            index=option_index(parking_options, parking),
            key="detail_residential_parking",
        )
        elevator_options = ["미확인", "있음", "없음"]
        elevator = c2.selectbox(
            "엘리베이터", elevator_options,
            index=option_index(elevator_options, elevator),
            key="detail_residential_elevator",
        )
        extra["관리비 포함 항목"] = c3.text_input("관리비 포함 항목", key="detail_maintenance_items")
        extra["즉시 입주 가능 여부"] = c3.selectbox(
            "즉시 입주 가능 여부", ["미확인", "가능", "불가"], key="detail_immediate_move_in"
        )
        extra["준공연도"] = c4.number_input("준공연도", min_value=0, max_value=2100, step=1, key="detail_residential_year")
        extra["옵션"] = c4.text_input("옵션", key="detail_residential_options")
    elif selected_type in ["상가", "사무실"]:
        c1, c2, c3 = st.columns(3)
        extra["권리금(만원)"] = c1.number_input("권리금(만원)", min_value=0.0, step=100.0, key="detail_commercial_premium")
        extra["업종 제한"] = c1.selectbox("업종 제한 여부", ["미확인", "없음", "있음"], key="detail_business_restriction")
        parking_options = ["미확인", "가능", "불가"]
        parking = c2.selectbox(
            "주차 가능 여부", parking_options,
            index=option_index(parking_options, parking),
            key="detail_commercial_parking",
        )
        extra["현재 임차인 여부"] = c2.selectbox(
            "현재 임차인 여부", ["미확인", "있음", "없음"], key="detail_current_tenant"
        )
        extra["유동인구 메모"] = c3.text_area("유동인구 메모", key="detail_foot_traffic")
    elif selected_type == "토지":
        c1, c2, c3, c4 = st.columns(4)
        extra["지목"] = c1.text_input("지목", key="detail_land_category")
        extra["용도지역"] = c2.text_input("용도지역", key="detail_land_zone")
        extra["허용 건폐율(%)"] = c1.number_input("허용 건폐율(%)", min_value=0.0, step=1.0, key="detail_land_bcr")
        extra["허용 용적률(%)"] = c2.number_input("허용 용적률(%)", min_value=0.0, step=1.0, key="detail_land_far")
        extra["개발행위 가능 여부"] = c3.selectbox("개발행위 가능 여부", ["미확인", "가능", "불가"], key="detail_development")
        extra["농지전용 가능 여부"] = c3.selectbox("농지전용 가능 여부", ["미확인", "가능", "불가"], key="detail_farmland_conversion")
        extra["분할 가능 여부"] = c4.selectbox("분할 가능 여부", ["미확인", "가능", "불가"], key="detail_subdivision")
        extra["도로 접함 여부"] = c4.selectbox("도로 접함 여부", ["미확인", "접함", "접하지 않음"], key="detail_road_contact")
    elif selected_type in FACTORY_TYPES:
        c1, c2, c3, c4 = st.columns(4)
        extra["용도지역"] = c1.text_input("용도지역", key="detail_factory_zone")
        extra["준공연도"] = c1.number_input("준공연도", min_value=0, max_value=2100, step=1, key="detail_factory_year")
        extra["진입도로 폭(m)"] = c2.number_input("진입도로 폭(m)", min_value=0.0, step=0.5, key="detail_factory_road_width")
        extra["전력량(kW)"] = c2.number_input("전력량(kW)", min_value=0.0, step=10.0, key="detail_factory_power")
        extra["층고(m)"] = c2.number_input("층고(m)", min_value=0.0, step=0.5, key="detail_factory_ceiling")
        extra["상수도"] = c3.selectbox("상수도", ["미확인", "있음", "없음"], key="detail_factory_water")
        extra["하수도"] = c3.selectbox("하수도", ["미확인", "있음", "없음"], key="detail_factory_sewer")
        extra["호이스트"] = c3.selectbox("호이스트", ["미확인", "있음", "없음"], key="detail_factory_hoist")
        extra["폐수 가능 여부"] = c4.selectbox("폐수 가능 여부", ["미확인", "가능", "불가"], key="detail_factory_wastewater")
        extra["공장등록 가능 여부"] = c4.selectbox("공장등록 가능 여부", ["미확인", "가능", "불가"], key="detail_factory_registration")
        extra["대형차 진입 가능 여부"] = c4.selectbox("대형차 진입 가능 여부", ["미확인", "가능", "불가"], key="detail_factory_truck")

    st.markdown("#### 투자 정보")
    investment_yield = monthly_rent * 12 / (sale_price - deposit) * 100 if sale_price > deposit else 0
    i1, i2, i3, i4 = st.columns(4)
    i1.metric("예상 수익률", f"{investment_yield:.2f}%")
    vacancy = i1.selectbox("공실 여부", ["미확인", "공실", "임대중"], key="investment_vacancy")
    tenant = i2.selectbox("임차인 여부", ["미확인", "있음", "없음"], key="investment_tenant")
    contract_end = i2.text_input("계약만료일", placeholder="예: 2027-12-31", key="investment_contract_end")
    investment_memo = i3.text_area("투자 메모", key="investment_memo")
    favorite = i4.checkbox("★ 즐겨찾기", key="listing_favorite")

    st.markdown("#### 관리 정보")
    m1, m2, m3, m4 = st.columns(4)
    manager = m1.text_input("담당자", key="manager_name")
    contact = m2.text_input("연락처", key="manager_contact")
    visit_date = m3.text_input("현장방문일", placeholder="예: 2026-06-10", key="management_visit_date")
    property_status = m4.selectbox("매물 상태", PROPERTY_STATUSES, key="management_property_status")

    st.markdown("#### 중개사무소 정보")
    a1, a2, a3, a4 = st.columns(4)
    agency_name = a1.text_input("중개사무소명", value=str(auto.get("agency_name", "")), key="agency_name_detail")
    agency_owner = a1.text_input("대표자명", value=str(auto.get("agency_owner", "")), key="agency_owner_detail")
    agent_name = a2.text_input("담당자", value=str(auto.get("agent_name", "")), key="agent_name_detail")
    agent_phone = a2.text_input("연락처", value=str(auto.get("agent_phone", "")), key="agent_phone_detail")
    office_phone = a2.text_input("사무실 전화번호", value=str(auto.get("office_phone", "")), key="office_phone_detail")
    mobile_phone = a2.text_input("휴대폰 번호", value=str(auto.get("mobile_phone", "")), key="mobile_phone_detail")
    agency_address = a3.text_input("사무실 주소", value=str(auto.get("agency_address", "")), key="agency_address_detail")
    agency_registration = a3.text_input(
        "등록번호", value=str(auto.get("agency_registration_number", "")), key="agency_registration_detail"
    )
    platforms = ["", "네이버부동산", "직방", "다방", "기타"]
    platform = a4.selectbox(
        "플랫폼", platforms, index=option_index(platforms, auto.get("platform", "")), key="agency_platform_detail"
    )
    first_seen_at = a4.text_input("최초 확인일", value=str(auto.get("first_seen_at", "")), key="agency_first_seen_detail")
    last_seen_at = a4.text_input("마지막 확인일", value=str(auto.get("last_seen_at", "")), key="agency_last_seen_detail")

    st.markdown("#### 중개/출처 정보")
    p1, p2, p3 = st.columns(3)
    provider_agency_name = p1.text_input(
        "제공 부동산", value=str(auto.get("provider_agency_name", "")), key="source_provider_agency"
    )
    listing_provider = p1.text_input(
        "제공처", value=str(auto.get("listing_provider", "")), key="source_listing_provider"
    )
    verified_options = ["", "확인매물", "미확인"]
    is_verified_listing = p2.selectbox(
        "확인매물 여부", verified_options,
        index=option_index(verified_options, auto.get("is_verified_listing", "")),
        key="source_verified_listing",
    )
    verified_date = p2.text_input(
        "확인일", value=str(auto.get("verified_date", "")), key="source_verified_date"
    )
    listed_date = p3.text_input(
        "등록일", value=str(auto.get("listed_date", "")), key="source_listed_date"
    )
    updated_date = p3.text_input(
        "수정일", value=str(auto.get("updated_date", "")), key="source_updated_date"
    )

    submitted = st.form_submit_button("매물 저장", use_container_width=True, key="listing_submit")

if submitted:
    if not name.strip():
        st.error("매물명을 입력하세요.")
    elif listing_url_key(naver_link) and listing_url_key(naver_link) in {
        listing_url_key(url)
        for url in st.session_state.listings["네이버부동산 링크"].fillna("")
    }:
        st.error("이미 등록된 매물입니다")
    else:
        photo_name, photo_data = encode_photo(photo)
        row = {
            "매물명": name.strip(), "주소": address.strip(), "지역": get_region(address),
            "매물종류": selected_type, "거래유형": deal_type,
            "네이버 매물 ID": extract_naver_article_id(naver_link),
            "네이버부동산 링크": naver_link.strip(), "사진 파일명": photo_name,
            "naver_url": naver_link.strip(), "naver_article_id": extract_naver_article_id(naver_link),
            "auto_collected": "아니오", "collected_at": "",
            "source_search_url": str(auto.get("source_search_url", "")),
            "extraction_status": "수동 등록", "extraction_error": "",
            "사진 데이터": photo_data, "매매가(만원)": sale_price,
            "전세금(만원)": jeonse_price, "보증금(만원)": deposit, "월세(만원)": monthly_rent,
            "관리비(만원)": maintenance_fee, "대지면적(㎡)": land_area,
            "전용면적(㎡)": exclusive_area, "공급면적(㎡)": supply_area,
            "건물면적(㎡)": building_area, "층수": floor,
            "주차 가능 여부": parking, "엘리베이터": elevator, "메모": memo.strip(),
            "예상 수익률(%)": investment_yield, "공실 여부": vacancy,
            "임차인 여부": tenant, "계약만료일": contract_end.strip(),
            "투자 메모": investment_memo.strip(), "담당자": manager.strip(),
            "연락처": contact.strip(), "현장방문일": visit_date.strip(),
            "매물 상태": property_status, "즐겨찾기": "★" if favorite else "",
            "agency_name": agency_name.strip(), "agency_owner": agency_owner.strip(),
            "agent_name": agent_name.strip(), "agent_phone": agent_phone.strip(),
            "office_phone": office_phone.strip(), "mobile_phone": mobile_phone.strip(),
            "agency_address": agency_address.strip(),
            "agency_registration_number": agency_registration.strip(),
            "platform": platform,
            "provider_agency_name": provider_agency_name.strip(),
            "listing_provider": listing_provider.strip(),
            "is_verified_listing": is_verified_listing,
            "verified_date": verified_date.strip(), "listed_date": listed_date.strip(),
            "updated_date": updated_date.strip(),
            "first_seen_at": first_seen_at.strip() or datetime.now().isoformat(timespec="seconds"),
            "last_seen_at": last_seen_at.strip() or datetime.now().isoformat(timespec="seconds"),
            **extra,
        }
        row.update(calculate(row))
        row.update(generate_ai_analysis(row))
        st.session_state.listings = pd.concat(
            [st.session_state.listings, pd.DataFrame([row])], ignore_index=True
        ).reindex(columns=COLUMNS)
        save_listings(st.session_state.listings)
        st.session_state.extracted_listing = {}
        st.session_state.naver_extract_url = ""
        st.session_state.extraction_logs = []
        st.session_state.search_result_listings = []
        st.session_state.detected_url_type = ""
        st.success("매물을 저장했습니다.")

st.subheader("검색 및 필터")
f1, f2, f3, f4, f5, f6 = st.columns(6)
with f1:
    keyword = st.text_input("키워드 검색", placeholder="매물명, 주소, 메모, 옵션", key="filter_keyword")
    type_filter = st.multiselect("매물종류", PROPERTY_TYPES, key="filter_property_type")
with f2:
    region_keyword = st.text_input("지역 검색", placeholder="예: 화성시, 강남구", key="filter_region_keyword")
    regions = sorted(st.session_state.listings["지역"].dropna().astype(str).unique())
    region_filter = st.multiselect("지역", regions, key="filter_region")
    deal_filter = st.multiselect("거래유형", DEAL_TYPES, key="filter_deal_type")
with f3:
    min_price = st.number_input("최소 매매가(만원)", min_value=0.0, step=1000.0, key="filter_min_price")
    max_price = st.number_input("최대 매매가(만원, 0=제한없음)", min_value=0.0, step=1000.0, key="filter_max_price")
with f4:
    min_rent = st.number_input("최소 월세(만원)", min_value=0.0, step=10.0, key="filter_min_rent")
    max_rent = st.number_input("최대 월세(만원, 0=제한없음)", min_value=0.0, step=10.0, key="filter_max_rent")
    sort_order = st.selectbox(
        "정렬", ["입력 순", "수익률 높은 순", "평당가 낮은 순", "매매가 낮은 순", "매매가 높은 순"],
        key="filter_sort_order",
    )
with f5:
    managers = sorted(
        value for value in st.session_state.listings["담당자"].dropna().astype(str).unique() if value
    )
    manager_filter = st.multiselect("담당자", managers, key="filter_manager")
    status_filter = st.multiselect("매물 상태", PROPERTY_STATUSES, key="filter_status")
    favorites_only = st.checkbox("★ 즐겨찾기만 보기", key="filter_favorites")
with f6:
    agency_names = sorted(
        value for value in st.session_state.listings["agency_name"].dropna().astype(str).unique() if value
    )
    agency_filter = st.multiselect("중개사무소", agency_names, key="filter_agency")
    agency_contacts = sorted({
        value
        for column in ["agent_phone", "office_phone", "mobile_phone"]
        for value in st.session_state.listings[column].dropna().astype(str).unique()
        if value
    })
    agency_contact_filter = st.multiselect("중개사 연락처", agency_contacts, key="filter_agency_contact")

filtered = filter_listings(
    st.session_state.listings,
    keyword=keyword,
    region_keyword=region_keyword,
    property_types=type_filter,
    regions=region_filter,
    deal_types=deal_filter,
    managers=manager_filter,
    statuses=status_filter,
    favorites_only=favorites_only,
    agencies=agency_filter,
    agency_contacts=agency_contact_filter,
    min_price=min_price,
    max_price=max_price,
    min_rent=min_rent,
    max_rent=max_rent,
    sort_order=sort_order,
)

with st.expander("중개사무소별 매물 보기", expanded=False):
    agency_rows = filtered[filtered["agency_name"].fillna("").astype(str) != ""]
    if agency_rows.empty:
        st.info("저장된 중개사무소 정보가 없습니다.")
    else:
        agency_counts = (
            agency_rows.groupby(["agency_name", "office_phone", "mobile_phone"], dropna=False)
            .size().reset_index(name="매물 개수").sort_values("매물 개수", ascending=False)
        )
        st.dataframe(agency_counts, use_container_width=True, hide_index=True)

        compare = agency_rows.copy()
        compare["비교 키"] = (
            compare["주소"].fillna("").astype(str) + "|"
            + compare["매매가(만원)"].fillna(0).astype(str) + "|"
            + compare["전용면적(㎡)"].fillna(0).astype(str)
        )
        duplicate_keys = compare.groupby("비교 키")["agency_name"].nunique()
        duplicates = compare[compare["비교 키"].isin(duplicate_keys[duplicate_keys > 1].index)]
        st.markdown("##### 여러 중개사무소에 등록된 동일 조건 매물")
        if duplicates.empty:
            st.caption("비교 가능한 중복 매물이 없습니다.")
        else:
            st.dataframe(
                duplicates[["매물명", "주소", "매매가(만원)", "전용면적(㎡)", "agency_name", "agent_phone"]],
                use_container_width=True, hide_index=True,
            )

tabs = st.tabs(["전체", *PROPERTY_TYPES])
with tabs[0]:
    show_table(filtered, "전체")
for index, property_type in enumerate(PROPERTY_TYPES, start=1):
    with tabs[index]:
        show_table(filtered[filtered["매물종류"] == property_type], property_type)

with st.expander("AI 매물 요약 및 점수", expanded=False):
    if filtered.empty:
        st.info("표시할 매물이 없습니다.")
    else:
        summary_options = {
            f"{index + 1}. {row['매물명']}": row
            for index, (_, row) in enumerate(filtered.iterrows())
        }
        summary_choice = st.selectbox("요약을 볼 매물", list(summary_options), key="ai_summary_choice")
        summary_row = summary_options[summary_choice]
        s1, s2, s3, s4, s5, s6 = st.columns(6)
        s1.metric("입지", f"{summary_row['ai_location_score']:.0f}")
        s2.metric("가격 경쟁력", f"{summary_row['ai_price_score']:.0f}")
        s3.metric("접근성", f"{summary_row['ai_access_score']:.0f}")
        s4.metric("투자성", f"{summary_row['ai_investment_score']:.0f}")
        s5.metric("희소성", f"{summary_row['ai_scarcity_score']:.0f}")
        s6.metric("총점", f"{summary_row['ai_total_score']:.0f}점")
        st.text(summary_row["ai_summary"])

st.info(
    "Streamlit Community Cloud 내부 CSV는 영구 저장이 보장되지 않습니다. "
    "사용 후 전체 CSV를 다운로드해 백업하세요."
)
