# -*- coding: utf-8 -*-
"""Normalize listing deal prices and area values across collectors and the app."""

import re
from datetime import datetime, timedelta, timezone


PYEONG_M2 = 3.305785
PRICE_KEYS = ("매매가(만원)", "전세금(만원)", "보증금(만원)", "월세(만원)")
AREA_KEYS = (
    ("대지면적", "land"),
    ("건물면적", "building"),
    ("전용면적", "exclusive"),
    ("공급면적", "supply"),
)
DETAIL_PATTERNS = {
    "총층수": r"(?:총층수|총\s*층)\s*[:：]?\s*(\d+)",
    "방향": r"(?:방향|주실방향)\s*[:：]?\s*([가-힣]+향)",
    "사용승인일": r"(?:사용승인일|사용승인|준공일)\s*[:：]?\s*(\d{2,4}[./-]\d{1,2}[./-]\d{1,2})",
    "주차대수": r"(?:주차대수|총주차대수|주차)\s*[:：]?\s*([\d,.]+)\s*대",
    "관리비(만원)": r"관리비\s*[:：]?\s*([\d,.]+)\s*만?",
    "방 개수": r"(?:방수|방\s*개수|방)\s*[:：]?\s*(\d+)",
    "욕실 수": r"(?:욕실수|욕실\s*개수|욕실)\s*[:：]?\s*(\d+)",
}


def parse_number(value):
    match = re.search(r"-?[\d,.]+", str(value))
    return float(match.group().replace(",", "")) if match else 0.0


def parse_price(value):
    text = re.sub(r"\s+", "", str(value)).replace(",", "")
    total = 0.0
    for pattern, multiplier in (
        (r"([\d.]+)억", 10000),
        (r"([\d.]+)천", 1000),
        (r"([\d.]+)백", 100),
    ):
        total += sum(float(match) * multiplier for match in re.findall(pattern, text))
    if total:
        remainder = re.sub(r"[\d.]+(?:억|천|백)", "", text).replace("만", "")
        return total + parse_number(remainder)
    return parse_number(text)


def parse_deal_and_price(text):
    """Use only a deal label immediately followed by its price."""
    source = str(text).replace("\r\n", "\n")
    patterns = (
        r"(?:^|\n)\s*(월세)\s*[:：]?\s*([\d,.억천백만\s]+\s*/\s*[\d,.억천백만\s]+)",
        r"(?:^|\n)\s*(매매|전세)\s*[:：]?\s*([\d,.억천백만\s]+)",
        r"\b(월세)\s*[:：]?\s*([\d,.억천백만]+\s*/\s*[\d,.억천백만]+)",
        r"\b(매매|전세)\s*[:：]?\s*([\d,.억천백만]+(?:\s+[\d,.억천백만]+)?)",
    )
    match = next((found for pattern in patterns if (found := re.search(pattern, source))), None)
    deal_type = match.group(1) if match else "기타"
    price_text = re.sub(r"\s+", " ", match.group(2)).strip() if match else ""
    result = {
        "거래유형": deal_type,
        "parsed_price_text": price_text,
        "매매가(만원)": 0.0,
        "전세금(만원)": 0.0,
        "보증금(만원)": 0.0,
        "월세(만원)": 0.0,
    }
    if deal_type == "월세":
        deposit, monthly_rent = re.split(r"\s*/\s*", price_text, maxsplit=1)
        result["보증금(만원)"] = parse_price(deposit)
        result["월세(만원)"] = parse_price(monthly_rent)
    elif deal_type == "매매":
        result["매매가(만원)"] = parse_price(price_text)
    elif deal_type == "전세":
        result["전세금(만원)"] = parse_price(price_text)
    return result


def normalize_financial_fields(row):
    """Keep only the price fields valid for the selected deal type."""
    item = dict(row)
    deal_type = str(item.get("거래유형", "")).strip()
    values = {key: parse_number(item.get(key, 0)) for key in PRICE_KEYS}
    if deal_type == "매매":
        values.update({"전세금(만원)": 0.0, "보증금(만원)": 0.0, "월세(만원)": 0.0})
    elif deal_type == "전세":
        values.update({"매매가(만원)": 0.0, "보증금(만원)": 0.0, "월세(만원)": 0.0})
    elif deal_type == "월세":
        values.update({"매매가(만원)": 0.0, "전세금(만원)": 0.0})
    item.update(values)
    return item


def normalize_area_fields(row):
    """Synchronize numeric square-meter and pyeong columns."""
    item = dict(row)
    for korean, english in AREA_KEYS:
        m2 = parse_number(item.get(f"{korean}(㎡)", 0) or item.get(f"{english}_area_m2", 0))
        pyeong = round(m2 / PYEONG_M2, 2) if m2 else 0.0
        item[f"{korean}(㎡)"] = round(m2, 2)
        item[f"{korean}(평)"] = pyeong
        item[f"{english}_area_m2"] = round(m2, 2)
        item[f"{english}_area_pyeong"] = pyeong
    return item


def parse_detail_fields(text):
    source = re.sub(r"\s+", " ", str(text))
    result = {}
    floor = re.search(r"(?:해당층|층수)\s*[:：]?\s*(\d+)", source)
    if floor:
        result["층수"] = parse_number(floor.group(1))
    for key, pattern in DETAIL_PATTERNS.items():
        match = re.search(pattern, source)
        if match:
            result[key] = parse_number(match.group(1)) if key not in ("방향", "사용승인일") else match.group(1)
    return result


def parse_datetime(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def normalize_status_fields(row, now_value=None):
    item = dict(row)
    now_value = now_value or datetime.now().astimezone()
    first_seen = parse_datetime(item.get("first_seen_at") or item.get("collected_at"))
    item["first_seen_at"] = (
        first_seen.isoformat(timespec="seconds")
        if first_seen
        else str(item.get("first_seen_at") or item.get("collected_at") or "")
    )
    age = now_value - first_seen.astimezone(now_value.tzinfo) if first_seen else None
    item["is_new"] = "신규" if age is not None and timedelta(0) <= age <= timedelta(hours=24) else ""
    change = parse_number(item.get("price_change_amount", 0))
    item["price_change_status"] = "가격 상승" if change > 0 else "가격 하락" if change < 0 else "변동 없음"
    item["price_change_text"] = (
        f"▲ {abs(change):,.0f}만원 상승"
        if change > 0
        else f"▼ {abs(change):,.0f}만원 하락"
        if change < 0
        else "변동 없음"
    )
    item["latitude"] = parse_number(item.get("latitude", 0))
    item["longitude"] = parse_number(item.get("longitude", 0))
    return item


def normalize_listing(row):
    item = dict(row)
    details = parse_detail_fields(item.get("detail_text") or item.get("raw_card_text", ""))
    for key, value in details.items():
        if not item.get(key):
            item[key] = value
    return normalize_status_fields(normalize_area_fields(normalize_financial_fields(item)))
