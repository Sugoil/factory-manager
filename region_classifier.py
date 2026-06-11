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


def classify_cheongju_region(*values, default_city=True):
    text = " ".join(str(value or "") for value in values)
    text = re.sub(r"\s+", " ", text).strip()
    neighborhood = next((name for name in NEIGHBORHOODS if name in text), "")
    district = next((name for name in DISTRICTS if name in text), "")
    if not district and neighborhood:
        district = NEIGHBORHOOD_TO_DISTRICT[neighborhood]
    city = "청주시" if default_city or "청주시" in text or district or neighborhood else ""
    return {"city": city, "district": district, "neighborhood": neighborhood}


def enrich_listing_region(row):
    item = dict(row)
    region = classify_cheongju_region(
        item.get("주소", ""),
        item.get("매물명", ""),
        item.get("raw_card_text", ""),
        item.get("source_search_url", ""),
        item.get("지역", ""),
    )
    item.update(region)
    item["지역"] = region["neighborhood"] or region["district"] or region["city"] or item.get("지역", "")
    return item
