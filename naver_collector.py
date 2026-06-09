"""Small, rate-limited Naver Real Estate watcher for GitHub Actions."""

from __future__ import annotations

import csv
import json
import os
import re
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).parent
CSV_FILE = ROOT / "listings.csv"
LOG_FILE = ROOT / "logs" / "naver_collector.log"
PYEONG = 3.3058
DEFAULT_DELAY_SECONDS = 6
DEFAULT_MAX_DETAILS = 10

COLUMNS = [
    "매물명", "주소", "지역", "매물종류", "거래유형", "네이버부동산 링크",
    "사진 파일명", "사진 데이터", "매매가(만원)", "보증금(만원)", "월세(만원)",
    "관리비(만원)", "권리금(만원)", "대지면적(㎡)", "전용면적(㎡)", "공급면적(㎡)",
    "건축면적(㎡)", "건물면적(㎡)", "대지면적(평)", "전용면적(평)", "공급면적(평)",
    "건물면적(평)", "평당가 기준", "평당가(만원)", "월세 수익률(%)", "전세가율(%)",
    "매매가 대비 보증금 비율(%)", "방 개수", "욕실 수", "층수", "주차 가능 여부",
    "엘리베이터", "옵션", "준공연도", "용도지역", "업종 제한", "유동인구 메모",
    "지목", "도로 접함 여부", "개발 가능성 메모", "진입도로 폭(m)", "전력량(kW)",
    "상수도", "하수도", "호이스트", "폐수 가능 여부", "공장등록 가능 여부",
    "대형차 진입 가능 여부", "건폐율(%)", "용적률(%)", "전력당 가격(만원/kW)",
    "메모",
]


def log(message: str) -> None:
    LOG_FILE.parent.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    line = f"{timestamp} {message}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def env_list(name: str) -> list[str]:
    value = os.getenv(name, "")
    return [item.strip() for item in re.split(r"[\n,]", value) if item.strip()]


def env_number(name: str, default: float = 0) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def fetch_html(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc.endswith("naver.com"):
        raise ValueError("naver.com URL만 확인할 수 있습니다.")
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/124 Safari/537.36"
            )
        },
    )
    with urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8", errors="ignore")


def collect_json_objects(value, result: list[dict]) -> None:
    if isinstance(value, dict):
        result.append(value)
        for child in value.values():
            collect_json_objects(child, result)
    elif isinstance(value, list):
        for child in value:
            collect_json_objects(child, result)


def extract_objects(html: str) -> list[dict]:
    objects: list[dict] = []
    for script in re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.I | re.S):
        try:
            collect_json_objects(json.loads(script), objects)
        except (json.JSONDecodeError, TypeError):
            continue
    return objects


def first_value(objects: list[dict], keys: list[str]):
    for obj in objects:
        for key in keys:
            value = obj.get(key)
            if value not in (None, "", [], {}):
                return value
    return ""


def parse_number(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").replace(" ", "")
    if not text:
        return 0
    total = 0.0
    eok = re.search(r"(\d+(?:\.\d+)?)억", text)
    manwon = re.search(r"(\d+(?:\.\d+)?)만", text)
    if eok:
        total += float(eok.group(1)) * 10000
    if manwon:
        total += float(manwon.group(1))
    if total:
        return total
    number = re.search(r"\d+(?:\.\d+)?", text)
    return float(number.group()) if number else 0


def normalize_property_type(value: str) -> str:
    text = str(value)
    for item in [
        "공장", "창고", "토지", "상가", "원룸", "투룸", "쓰리룸",
        "아파트", "빌라", "오피스텔", "사무실",
    ]:
        if item in text:
            return item
    return "기타"


def normalize_deal_type(value: str) -> str:
    text = str(value)
    for item in ["매매", "전세", "월세"]:
        if item in text:
            return item
    return "매매"


def get_region(address: str) -> str:
    return address.strip().split()[0] if address.strip() else "지역 미입력"


def listing_key(url: str) -> str:
    article_no = re.search(r"(?:articleNo=|/articles/)(\d+)", url)
    if article_no:
        return f"article:{article_no.group(1)}"
    return url.split("#", 1)[0].rstrip("/")


def calculate(row: dict) -> None:
    sale = parse_number(row["매매가(만원)"])
    deposit = parse_number(row["보증금(만원)"])
    rent = parse_number(row["월세(만원)"])
    for name in ["대지면적", "전용면적", "공급면적", "건물면적"]:
        row[f"{name}(평)"] = round(parse_number(row[f"{name}(㎡)"]) / PYEONG, 2)

    if row["매물종류"] == "토지":
        area_name = "대지면적"
    elif row["매물종류"] in ["공장", "창고"]:
        area_name = "건물면적" if parse_number(row["건물면적(㎡)"]) else "대지면적"
    else:
        area_name = "전용면적" if parse_number(row["전용면적(㎡)"]) else "건물면적"
    area_pyeong = parse_number(row.get(f"{area_name}(평)", 0))
    row["평당가 기준"] = area_name
    row["평당가(만원)"] = round(sale / area_pyeong, 2) if area_pyeong else 0
    row["월세 수익률(%)"] = round(rent * 12 / (sale - deposit) * 100, 2) if sale > deposit else 0
    row["전세가율(%)"] = round(deposit / sale * 100, 2) if row["거래유형"] == "전세" and sale else 0
    row["매매가 대비 보증금 비율(%)"] = round(deposit / sale * 100, 2) if sale else 0


def extract_listing(url: str) -> dict | None:
    html = fetch_html(url)
    objects = extract_objects(html)
    page_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(html))).strip()
    address = str(first_value(objects, ["roadAddress", "jibunAddress", "address", "location"]))
    if not address:
        match = re.search(r"([가-힣]+(?:시|도)\s+[가-힣]+(?:시|군|구)[^|]{0,50})", page_text)
        address = match.group(1).strip() if match else ""

    row = {column: "" for column in COLUMNS}
    row.update(
        {
            "매물명": str(first_value(objects, ["articleName", "buildingName", "complexName"]))
            or f"네이버 매물 {datetime.now().strftime('%Y%m%d')}",
            "주소": address,
            "지역": get_region(address),
            "매물종류": normalize_property_type(
                first_value(objects, ["realEstateTypeName", "articleName", "buildingTypeName"])
            ),
            "거래유형": normalize_deal_type(first_value(objects, ["tradeTypeName", "tradeType"])),
            "네이버부동산 링크": url,
            "매매가(만원)": parse_number(first_value(objects, ["dealOrWarrantPrc", "dealPrice", "price"])),
            "보증금(만원)": parse_number(first_value(objects, ["warrantPrice", "deposit", "depositPrice"])),
            "월세(만원)": parse_number(first_value(objects, ["rentPrc", "rentPrice", "monthlyRent"])),
            "관리비(만원)": parse_number(first_value(objects, ["maintenanceFee", "manageCost"])),
            "전용면적(㎡)": parse_number(first_value(objects, ["area2", "exclusiveArea"])),
            "공급면적(㎡)": parse_number(first_value(objects, ["area1", "supplyArea"])),
            "대지면적(㎡)": parse_number(first_value(objects, ["landArea"])),
            "건물면적(㎡)": parse_number(first_value(objects, ["buildingArea", "totalArea"])),
            "층수": parse_number(first_value(objects, ["floorInfo", "floor", "correspondingFloorCount"])),
            "방 개수": parse_number(first_value(objects, ["roomCount", "roomCnt"])),
            "욕실 수": parse_number(first_value(objects, ["bathroomCount", "bathroomCnt"])),
            "메모": "GitHub Actions 자동 수집",
        }
    )
    meaningful = bool(address or row["매매가(만원)"] or row["전용면적(㎡)"] or row["건물면적(㎡)"])
    if not meaningful:
        return None
    calculate(row)
    return row


def discover_urls(seed_url: str) -> list[str]:
    html = fetch_html(seed_url)
    urls = {seed_url} if "articleNo=" in seed_url or "/articles/" in seed_url else set()
    for match in re.findall(r"https?://[^\"' <]+", html):
        clean = unescape(match).replace("\\u002F", "/").replace("\\/", "/")
        if "new.land.naver.com" in clean and ("articleNo=" in clean or "/articles/" in clean):
            urls.add(clean)
    return sorted(urls)


def matches_filters(row: dict) -> bool:
    regions = env_list("WATCH_REGIONS")
    property_types = env_list("WATCH_PROPERTY_TYPES")
    deal_types = env_list("WATCH_DEAL_TYPES")
    address = str(row["주소"])
    if regions and not any(region in address for region in regions):
        return False
    if property_types and row["매물종류"] not in property_types:
        return False
    if deal_types and row["거래유형"] not in deal_types:
        return False
    checks = [
        ("매매가(만원)", "WATCH_MIN_PRICE", "WATCH_MAX_PRICE"),
        ("월세(만원)", "WATCH_MIN_RENT", "WATCH_MAX_RENT"),
    ]
    for column, min_name, max_name in checks:
        value = parse_number(row[column])
        minimum = env_number(min_name)
        maximum = env_number(max_name)
        if minimum and value < minimum:
            return False
        if maximum and value > maximum:
            return False
    return True


def load_existing() -> tuple[list[dict], set[str]]:
    if not CSV_FILE.exists():
        return [], set()
    with CSV_FILE.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    urls = {row.get("네이버부동산 링크", "").strip() for row in rows}
    return rows, {listing_key(url) for url in urls if url}


def save_rows(rows: list[dict]) -> None:
    with CSV_FILE.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in COLUMNS})


def main() -> int:
    seeds = env_list("NAVER_WATCH_URLS")
    if not seeds:
        log("SKIP: NAVER_WATCH_URLS가 설정되지 않았습니다.")
        return 0

    delay = max(env_number("REQUEST_DELAY_SECONDS", DEFAULT_DELAY_SECONDS), 5)
    max_details = min(max(int(env_number("MAX_DETAIL_REQUESTS", DEFAULT_MAX_DETAILS)), 1), 20)
    existing_rows, known_urls = load_existing()
    candidates: list[str] = []

    for seed in seeds[:5]:
        try:
            candidates.extend(discover_urls(seed))
            time.sleep(delay)
        except Exception as error:
            log(f"FAIL seed={seed} error={type(error).__name__}: {error}")

    new_rows = []
    for url in list(dict.fromkeys(candidates))[:max_details]:
        key = listing_key(url)
        if key in known_urls:
            continue
        try:
            row = extract_listing(url)
            if row and matches_filters(row):
                new_rows.append(row)
                known_urls.add(key)
                log(f"NEW url={url} address={row['주소']}")
            elif row:
                log(f"FILTERED url={url}")
            else:
                log(f"FAIL url={url} error=자동 추출 실패")
        except Exception as error:
            log(f"FAIL url={url} error={type(error).__name__}: {error}")
        time.sleep(delay)

    if new_rows:
        save_rows(existing_rows + new_rows)
    log(f"DONE seeds={len(seeds[:5])} candidates={len(candidates)} new={len(new_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
