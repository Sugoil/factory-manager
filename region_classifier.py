# -*- coding: utf-8 -*-
"""Cheongju city, district, and neighborhood classification helpers."""

import re


DISTRICTS = ("흥덕구", "청원구", "상당구", "서원구")
NEIGHBORHOOD_TO_DISTRICT = {
    "복대동": "흥덕구", "가경동": "흥덕구", "봉명동": "흥덕구", "운천동": "흥덕구",
    "오송읍": "흥덕구", "강내면": "흥덕구", "옥산면": "흥덕구",
    "율량동": "청원구", "사천동": "청원구", "오창읍": "청원구", "내수읍": "청원구",
    "북이면": "청원구",
    "용암동": "상당구", "금천동": "상당구", "탑동": "상당구", "문의면": "상당구",
    "산남동": "서원구", "성화동": "서원구", "개신동": "서원구", "분평동": "서원구",
    "사창동": "서원구", "사직동": "서원구", "남이면": "서원구",
}
NEIGHBORHOODS = tuple(NEIGHBORHOOD_TO_DISTRICT)
PROVINCE_PATTERN = r"(?:충청북도|충북)?"
DISTRICT_PATTERN = rf"(?:{'|'.join(map(re.escape, DISTRICTS))})"
NEIGHBORHOOD_PATTERN = rf"(?:{'|'.join(map(re.escape, NEIGHBORHOODS))})"


def classify_cheongju_region(*values, default_city=True):
    text = " ".join(str(value or "") for value in values)
    text = re.sub(r"\s+", " ", text).strip()
    neighborhood = next((name for name in NEIGHBORHOODS if name in text), "")
    district = next((name for name in DISTRICTS if name in text), "")
    if not district and neighborhood:
        district = NEIGHBORHOOD_TO_DISTRICT[neighborhood]
    city = "청주시" if default_city or "청주시" in text or district or neighborhood else ""
    return {"city": city, "district": district, "neighborhood": neighborhood}


def extract_full_address(*values):
    """Extract a Cheongju address, including a lot or road number when available."""
    text = " ".join(str(value or "") for value in values)
    text = re.sub(r"\s+", " ", text).strip()
    patterns = (
        rf"{PROVINCE_PATTERN}\s*청주시\s+{DISTRICT_PATTERN}\s+{NEIGHBORHOOD_PATTERN}"
        rf"(?:\s+(?:산\s*)?\d+(?:-\d+)?)?",
        rf"청주시\s+{DISTRICT_PATTERN}\s+{NEIGHBORHOOD_PATTERN}",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return re.sub(r"\s+", " ", match.group(0)).strip()
    return ""


def build_region_address(city="", district="", neighborhood=""):
    return " ".join(value for value in (city, district, neighborhood) if str(value).strip())


def enrich_listing_region(row):
    item = dict(row)
    source_values = (
        item.get("full_address", ""),
        item.get("주소", ""),
        item.get("raw_card_text", ""),
        item.get("매물명", ""),
        item.get("source_search_url", ""),
        item.get("지역", ""),
    )
    region = classify_cheongju_region(
        *source_values,
    )
    item.update(region)
    item["지역"] = region["neighborhood"] or region["district"] or region["city"] or item.get("지역", "")
    full_address = extract_full_address(*source_values)
    item["full_address"] = full_address or build_region_address(**region)
    return item
