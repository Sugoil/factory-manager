# -*- coding: utf-8 -*-
"""Collect visible listings from a user-opened Chrome tab through CDP."""

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from collection_settings import MAX_SAVE_PER_RUN
from region_classifier import classify_cheongju_region, enrich_listing_region
from db_store import (
    add_log,
    load_conditions,
    load_listings,
    replace_listings,
    upsert_collected_listing,
)


ROOT = Path(__file__).resolve().parent
CDP_URL = "http://localhost:9222"
LISTINGS_FILE = ROOT / "listings.csv"
LOG_FILE = ROOT / "collect_logs.csv"
MAX_NEW = MAX_SAVE_PER_RUN
REQUIRED_EXPORT_COLUMNS = [
    "city", "district", "neighborhood",
    "대지면적(㎡)", "대지면적(평)", "전용면적(㎡)", "전용면적(평)",
    "공급면적(㎡)", "공급면적(평)", "건물면적(㎡)", "건물면적(평)",
    "supply_area_m2", "supply_area_pyeong", "exclusive_area_m2", "exclusive_area_pyeong",
    "land_area_m2", "land_area_pyeong", "building_area_m2", "building_area_pyeong",
]
LAND_HOSTS = ("land.naver.com", "new.land.naver.com", "fin.land.naver.com")
REJECTED_PATHS = ("/news", "/404", "headline")
FAILURE_MESSAGE = (
    "start_chrome_debug.bat을 먼저 실행하고, "
    "네이버부동산에서 검색 결과 화면을 열어주세요."
)
BLOCKED_TEXTS = ("captcha", "비정상적인 접근", "접근이 제한", "요청이 너무 많")
PYEONG_M2 = 3.305785
SKIP_TITLE_TEXTS = (
    "본문 바로가기",
    "메뉴 바로가기",
    "지도 바로가기",
    "메뉴 접기",
    "메뉴 펼치기",
    "단지, 지역, 지하철, 초등학교 검색",
)
INVALID_UI_TERMS = (
    "본문 바로가기",
    "메뉴 접기",
    "지도 바로가기",
    "단지, 지역, 지하철, 초등학교 검색",
    "검색",
    "메뉴",
    "바로가기",
)


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_log(status, message="", url="", condition=None):
    condition_id = str((condition or {}).get("id", ""))
    collected_at = now()
    print(f"{status}: {message}")
    add_log(condition_id, status, url, message, collected_at)
    exists = LOG_FILE.exists()
    with LOG_FILE.open("a", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["수집시간", "조건ID", "상태", "URL", "메시지"],
        )
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "수집시간": collected_at,
                "조건ID": condition_id,
                "상태": status,
                "URL": url,
                "메시지": message,
            }
        )


def article_id(url):
    match = re.search(r"(?:articleNo=|articleId=|/articles?/)(\d+)", str(url))
    return match.group(1) if match else ""


def condition_region(condition):
    regions = (condition or {}).get("regions") or []
    for region in regions:
        value = str(region).strip()
        if value and "전체" not in value and "?" not in value and "�" not in value:
            return value
    return "청주시"


def contains_invalid_ui_text(text):
    clean = re.sub(r"\s+", " ", str(text)).strip()
    return any(term in clean for term in INVALID_UI_TERMS)


def parse_number(value):
    match = re.search(r"[\d,.]+", str(value))
    return float(match.group().replace(",", "")) if match else 0


def parse_price(value):
    text = re.sub(r"\s+", "", str(value)).replace(",", "")
    total = 0.0
    for pattern, multiplier in ((r"([\d.]+)억", 10000), (r"([\d.]+)천", 1000)):
        match = re.search(pattern, text)
        if match:
            total += float(match.group(1)) * multiplier
    if total:
        tail = re.search(r"(?:억|천)([\d.]+)(?:만)?", text)
        return total + (float(tail.group(1)) if tail else 0)
    return parse_number(text)


def parse_deal_and_price(card_text):
    """Parse the price line first so floor/area slash values cannot become monthly rent."""
    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in str(card_text).splitlines()
        if re.sub(r"\s+", " ", line).strip()
    ]
    price_line = next(
        (
            line for line in lines
            if re.match(r"^(?:매매|전세)\s+[\d,.]", line)
            or re.match(r"^월세\s+[\d,.억천만]+\s*/\s*[\d,.억천만]+", line)
        ),
        "",
    )
    if not price_line:
        price_line = next(
            (line for line in lines if re.search(r"\b(매매|전세|월세)\b", line)),
            "",
        )
    deal_match = re.search(r"\b(매매|전세|월세)\b", price_line)
    deal_type = deal_match.group(1) if deal_match else "기타"
    price_text = price_line[deal_match.end():].strip(" :：") if deal_match else ""
    result = {
        "거래유형": deal_type,
        "parsed_price_text": price_text,
        "매매가(만원)": 0,
        "전세금(만원)": 0,
        "보증금(만원)": 0,
        "월세(만원)": 0,
    }
    if deal_type == "월세":
        slash = re.search(r"([\d,.억천만]+)\s*/\s*([\d,.억천만]+)", price_text)
        if slash:
            result["보증금(만원)"] = parse_price(slash.group(1))
            result["월세(만원)"] = parse_price(slash.group(2))
    elif deal_type == "매매":
        result["매매가(만원)"] = parse_price(price_text)
    elif deal_type == "전세":
        result["전세금(만원)"] = parse_price(price_text)
    return result


def parse_area_fields(card_text):
    text = re.sub(r"\s+", " ", str(card_text))
    values = {"supply": 0.0, "exclusive": 0.0, "land": 0.0, "building": 0.0}
    labels = {
        "supply": ("공급면적", "공급"),
        "exclusive": ("전용면적", "전용"),
        "land": ("대지면적", "대지", "토지면적"),
        "building": ("건물면적", "연면적", "건물"),
    }
    for key, names in labels.items():
        pattern = rf"(?:{'|'.join(map(re.escape, names))})\s*[:：]?\s*([\d,.]+)\s*(㎡|m2|m²|평)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            area = parse_number(match.group(1))
            values[key] = area * PYEONG_M2 if match.group(2) == "평" else area
    unlabeled = re.search(r"([\d,.]+)\s*(?:㎡|m2|m²)", text, re.IGNORECASE)
    if unlabeled and not values["exclusive"]:
        values["exclusive"] = parse_number(unlabeled.group(1))
    result = {}
    for key, korean in (
        ("supply", "공급면적"),
        ("exclusive", "전용면적"),
        ("land", "대지면적"),
        ("building", "건물면적"),
    ):
        m2 = round(values[key], 2)
        pyeong = round(m2 / PYEONG_M2, 2) if m2 else 0
        result[f"{korean}(㎡)"] = m2
        result[f"{korean}(평)"] = pyeong
        result[f"{key}_area_m2"] = m2
        result[f"{key}_area_pyeong"] = pyeong
    return result


def detect_property_type(text):
    rules = (
        ("공장", ("공장",)),
        ("창고", ("창고",)),
        ("토지", ("토지", "대지", "땅")),
        ("상가", ("상가", "점포")),
        ("원룸", ("원룸",)),
        ("투룸", ("투룸",)),
        ("쓰리룸", ("쓰리룸", "3룸")),
        ("아파트", ("아파트",)),
        ("빌라", ("빌라", "다세대")),
        ("오피스텔", ("오피스텔",)),
        ("사무실", ("사무실", "오피스")),
    )
    return next((name for name, words in rules if any(word in text for word in words)), "기타")


def detect_deal_type(text):
    return parse_deal_and_price(text)["거래유형"]


def price_fields(text, deal_type):
    parsed = parse_deal_and_price(text)
    return {key: parsed[key] for key in ("매매가(만원)", "전세금(만원)", "보증금(만원)", "월세(만원)")}


def is_land_tab_url(url):
    parsed = urlparse(str(url))
    host = (parsed.hostname or "").lower()
    lowered = str(url).lower()
    return (
        any(host == allowed or host.endswith(f".{allowed}") for allowed in LAND_HOSTS)
        and not any(part in lowered for part in REJECTED_PATHS)
    )


def select_land_page(pages):
    candidates = [page for page in pages if is_land_tab_url(getattr(page, "url", ""))]
    if not candidates:
        return None

    def priority(page):
        url = str(page.url).lower()
        visible_route = any(route in url for route in ("/map", "/complexes", "/offices", "/houses"))
        return (0 if visible_route else 1, -len(url))

    return sorted(candidates, key=priority)[0]


def all_open_pages(browser):
    return [page for context in browser.contexts for page in context.pages]


def connect_to_open_tab(playwright, condition):
    try:
        browser = playwright.chromium.connect_over_cdp(CDP_URL)
    except Exception as error:
        raise RuntimeError(FAILURE_MESSAGE) from error
    write_log("CDP connected", CDP_URL, CDP_URL, condition)
    pages = all_open_pages(browser)
    urls = [str(page.url) for page in pages]
    write_log("Detected tabs", json.dumps(urls, ensure_ascii=False), condition=condition)
    page = select_land_page(pages)
    if page is None:
        raise RuntimeError(FAILURE_MESSAGE)
    page.bring_to_front()
    write_log("Selected tab", page.url, page.url, condition)
    return browser, page


def page_is_blocked(page):
    body_text = page.locator("body").inner_text(timeout=5000).lower()
    return any(text.lower() in body_text for text in BLOCKED_TEXTS)


def collect_visible_cards(page):
    selector = (
        "[data-article-no], [data-listing-id], [data-article-id], "
        "li[class*='item'], [class*='listing'], [class*='property'], "
        "[class*='article'], [class*='card']"
    )
    return page.locator(selector).evaluate_all(
        """
        elements => elements
          .filter(element => {
            const rect = element.getBoundingClientRect();
            if (!(rect.width > 0 && rect.height > 0 &&
                  rect.bottom >= 0 && rect.top <= window.innerHeight)) return false;
            const text = (element.innerText || '').replace(/\\s+/g, ' ').trim();
            const blocked = ['본문 바로가기', '메뉴 바로가기', '지도 바로가기'];
            const hasDeal = /(매매|전세|월세)/.test(text);
            const hasPrice = /\\d[\\d,.]*(?:억|천|만|\\s*\\/\\s*\\d)/.test(text);
            const hasDetail = /(㎡|m²|m2|평|층|아파트|오피스텔|빌라|상가|사무실|공장|창고|토지|원룸|투룸|쓰리룸)/i.test(text);
            return text.length >= 8 && text.length <= 1200 &&
                   !blocked.some(value => text === value) &&
                   hasDeal && hasPrice && hasDetail;
          })
          .map(element => {
            const card = element;
            const links = Array.from(card.querySelectorAll('a[href]'));
            const link = links.find(item =>
              /articleNo=|articleId=|\\/articles?\\//.test(item.href)
            ) || links.find(item => !item.href.includes('#')) || null;
            const articleNo = card.dataset?.articleNo || card.dataset?.articleId ||
              card.dataset?.listingId || '';
            return {
              url: link?.href || '',
              articleNo,
              text: (card.innerText || '').trim()
            };
          })
        """
    )


def parsed_price_has_value(parsed):
    return any(
        parsed.get(key, 0) > 0
        for key in ("매매가(만원)", "전세금(만원)", "보증금(만원)", "월세(만원)")
    )


def verify_uncertain_cards(context, cards, condition, max_details=MAX_NEW):
    checked = 0
    for card in cards:
        parsed = parse_deal_and_price(card.get("text", ""))
        if parsed["거래유형"] != "기타" and parsed_price_has_value(parsed):
            continue
        if checked >= max_details:
            break
        url = str(card.get("url", "")).strip()
        if not article_id(url):
            continue
        checked += 1
        detail_page = None
        try:
            detail_page = context.new_page()
            detail_page.goto(url, wait_until="domcontentloaded", timeout=30000)
            detail_page.wait_for_timeout(1500)
            detail_text = detail_page.locator("body").inner_text(timeout=10000)
            detail_parsed = parse_deal_and_price(detail_text)
            if detail_parsed["거래유형"] != "기타" and parsed_price_has_value(detail_parsed):
                card["detail_text"] = detail_text
                write_log("Detail verification success", article_id(url), url, condition)
            else:
                write_log("Detail verification failed", "거래유형 또는 가격을 확인하지 못했습니다.", url, condition)
        except Exception as error:
            write_log("Detail verification failed", f"{type(error).__name__}: {error}", url, condition)
        finally:
            if detail_page is not None:
                detail_page.close()
    return cards


def card_to_row(card, page_url, condition):
    raw_text = str(card.get("detail_text") or card.get("text", "")).strip()
    text = re.sub(r"\s+", " ", raw_text).strip()
    url = str(card.get("url", "")).strip()
    aid = str(card.get("articleNo", "")).strip() or article_id(url)
    lines = listing_lines(card)
    parsed_price = parse_deal_and_price(raw_text)
    deal_type = parsed_price["거래유형"]
    area_fields = parse_area_fields(raw_text)
    agency_match = re.search(r"([가-힣A-Za-z0-9 ]+(?:공인중개사사무소|부동산))", text)
    verified_match = re.search(r"확인매물|확인\s*\d{2}[./-]\d{2}[./-]\d{2}", text)
    date_match = re.search(r"\b(\d{2,4}[./-]\d{1,2}[./-]\d{1,2})\b", text)
    timestamp = now()
    region = condition_region(condition)
    row = {
        "매물명": make_listing_title(card),
        "주소": "",
        "지역": region,
        "매물종류": detect_property_type(text),
        "거래유형": deal_type,
        **area_fields,
        "네이버부동산 링크": url,
        "네이버 매물 ID": aid,
        "naver_url": url,
        "naver_article_id": aid,
        "provider_agency_name": agency_match.group(1).strip() if agency_match else "",
        "agency_name": agency_match.group(1).strip() if agency_match else "",
        "is_verified_listing": "확인매물" if verified_match else "",
        "verified_date": date_match.group(1) if date_match else "",
        "platform": "네이버부동산",
        "auto_collected": "예",
        "collected_at": timestamp,
        "first_seen_at": timestamp,
        "last_seen_at": timestamp,
        "source_search_url": page_url,
        "collection_condition": json.dumps(condition or {}, ensure_ascii=False, default=str),
        "extraction_status": "사용자 Chrome 화면 수집",
        "extraction_error": "",
        "매물 상태": "신규",
        "raw_card_text": str(card.get("text", "")).strip()[:2000],
        "parsed_deal_type": deal_type,
        "parsed_price_text": parsed_price["parsed_price_text"],
        "parsed_deposit": parsed_price["보증금(만원)"],
        "parsed_monthly_rent": parsed_price["월세(만원)"],
        "parsed_sale_price": parsed_price["매매가(만원)"],
        "parsed_jeonse_price": parsed_price["전세금(만원)"],
        "area_m2": area_fields["exclusive_area_m2"],
        "area_pyeong": area_fields["exclusive_area_pyeong"],
    }
    row.update({key: parsed_price[key] for key in ("매매가(만원)", "전세금(만원)", "보증금(만원)", "월세(만원)")})
    row = enrich_listing_region(row)
    detected_region = classify_cheongju_region(raw_text, card.get("text", ""), region)
    row.update(detected_region)
    row["지역"] = (
        detected_region["neighborhood"]
        or detected_region["district"]
        or detected_region["city"]
        or row["지역"]
    )
    return row


def log_parsed_listing(row, condition):
    url = str(row.get("naver_url", ""))
    for status, key in (
        ("raw_card_text", "raw_card_text"),
        ("parsed_deal_type", "parsed_deal_type"),
        ("parsed_price_text", "parsed_price_text"),
        ("parsed_deposit", "parsed_deposit"),
        ("parsed_monthly_rent", "parsed_monthly_rent"),
        ("parsed_sale_price", "parsed_sale_price"),
        ("parsed_jeonse_price", "parsed_jeonse_price"),
        ("area_m2", "area_m2"),
        ("area_pyeong", "area_pyeong"),
    ):
        message = str(row.get(key, ""))
        write_log(status, message[:2000], url, condition)


def unique_cards(cards):
    result = {}
    for card in cards:
        text = re.sub(r"\s+", " ", str(card.get("text", ""))).strip()
        url = str(card.get("url", "")).strip()
        aid = str(card.get("articleNo", "")).strip() or article_id(url)
        key = aid or url or text[:300]
        if key and aid and is_listing_card_text(text):
            result[key] = card
    return list(result.values())


def is_listing_card_text(text):
    clean = re.sub(r"\s+", " ", str(text)).strip()
    if not clean or contains_invalid_ui_text(clean):
        return False
    has_deal = bool(re.search(r"매매|전세|월세", clean))
    has_price = bool(re.search(r"\d[\d,.]*(?:억|천|만|\s*/\s*\d)", clean))
    has_detail = bool(
        re.search(
            r"㎡|m²|m2|평|층|아파트|오피스텔|빌라|상가|사무실|공장|창고|토지|원룸|투룸|쓰리룸",
            clean,
            re.IGNORECASE,
        )
    )
    return has_deal and has_price and has_detail and len(clean) <= 1200


def listing_lines(card):
    lines = []
    for raw_line in str(card.get("text", "")).splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line or contains_invalid_ui_text(line):
            continue
        if any(line.startswith(prefix) for prefix in ("본문 바로가기", "메뉴 바로가기", "지도 바로가기")):
            continue
        lines.append(line)
    return lines


def is_invalid_saved_listing(row):
    name = str(row.get("매물명", "")).strip()
    return contains_invalid_ui_text(name)


def cleanup_invalid_ui_listings():
    rows = load_listings()
    cleaned = []
    for row in rows:
        if is_invalid_saved_listing(row):
            continue
        item = dict(row)
        item = enrich_listing_region(item)
        cleaned.append(item)
    removed = len(rows) - len(cleaned)
    if removed or cleaned != rows:
        replace_listings(cleaned)
        export_csv()
    return removed


def save_candidate_cards(cards, page_url, condition, max_new=MAX_NEW):
    existing_rows = load_listings()
    known_ids = {
        str(row.get("naver_article_id") or row.get("네이버 매물 ID", "")).strip()
        for row in existing_rows
    }
    known_urls = {
        str(row.get("naver_url") or row.get("네이버부동산 링크", "")).strip()
        for row in existing_rows
    }
    known_ids.discard("")
    known_urls.discard("")

    new_count = 0
    duplicate_count = 0
    price_changed_count = 0
    limit_skipped_count = 0
    for card in cards:
        url = str(card.get("url", "")).strip()
        aid = str(card.get("articleNo", "")).strip() or article_id(url)
        is_known = aid in known_ids or url in known_urls
        if not is_known and new_count >= max_new:
            limit_skipped_count += 1
            continue
        row = card_to_row(card, page_url, condition)
        log_parsed_listing(row, condition)
        status = upsert_collected_listing(row)
        if status == "new":
            new_count += 1
            known_ids.add(aid)
            known_urls.add(url)
        elif status == "price_changed":
            price_changed_count += 1
            duplicate_count += 1
        else:
            duplicate_count += 1
    return new_count, duplicate_count, price_changed_count, limit_skipped_count


def make_listing_title(card):
    lines = listing_lines(card)
    if not lines:
        return "화면 수집 매물"

    non_price_lines = [
        line for line in lines
        if not re.fullmatch(r"(?:매매|전세|월세)?\s*[\d,.억천만/\s]+", line)
        and not re.fullmatch(r"[\d,.]+\s*(?:㎡|m²|m2|평)", line, re.IGNORECASE)
    ]
    for line in non_price_lines:
        if re.search(r"아파트|오피스텔|빌라|상가|사무실|공장|창고|토지|원룸|투룸|쓰리룸|동|리|로|길", line):
            return line[:100]

    deal = next((line for line in lines if re.search(r"매매|전세|월세", line)), "")
    area = next((line for line in lines if re.search(r"㎡|m²|m2|평", line, re.IGNORECASE)), "")
    base = non_price_lines[0] if non_price_lines else ""
    generated = " ".join(dict.fromkeys(part for part in (base, deal, area) if part))
    return generated[:100] or "화면 수집 매물"


def first_listing_summary(cards):
    if not cards:
        return "", ""
    text = str(cards[0].get("text", "")).strip()
    title = make_listing_title(cards[0])
    price_match = re.search(
        r"(?:매매|전세|월세|가격)\s*[:：]?\s*"
        r"([\d,.]+\s*억(?:\s*[\d,.]+\s*(?:천|만))?|[\d,.]+\s*/\s*[\d,.]+|[\d,.]+\s*만?)",
        text,
    )
    price = price_match.group(0).strip() if price_match else "가격을 찾지 못했습니다"
    return title, price


def export_csv():
    rows = load_listings()
    if not rows:
        return
    columns = list(dict.fromkeys([*(key for row in rows for key in row), *REQUIRED_EXPORT_COLUMNS]))
    with LISTINGS_FILE.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(
            [
                {
                    **{column: 0 for column in REQUIRED_EXPORT_COLUMNS},
                    **row,
                }
                for row in rows
            ]
        )


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright가 설치되어 있지 않습니다.")
        print("python -m pip install -r requirements.txt")
        return 2

    conditions = [item for item in load_conditions() if item.get("enabled", True)]
    condition = conditions[0] if conditions else {}
    write_log("Collection time", now(), condition=condition)
    removed_ui_rows = cleanup_invalid_ui_listings()
    write_log("Removed existing UI items", str(removed_ui_rows), condition=condition)
    new_count = 0
    duplicate_count = 0

    try:
        with sync_playwright() as playwright:
            _, page = connect_to_open_tab(playwright, condition)
            page.wait_for_timeout(1500)
            if page_is_blocked(page):
                raise RuntimeError("CAPTCHA 또는 접근 제한 화면이 감지되었습니다.")
            candidate_cards = collect_visible_cards(page)
            cards = unique_cards(candidate_cards)
            cards = verify_uncertain_cards(page.context, cards, condition)
            excluded_count = len(candidate_cards) - len(cards)
            write_log("Candidate cards found", str(len(candidate_cards)), page.url, condition)
            write_log("Excluded UI items", str(excluded_count), page.url, condition)
            write_log("Listing cards found", str(len(cards)), page.url, condition)
            write_log("Candidate listings", str(len(cards)), page.url, condition)
            first_title, first_price = first_listing_summary(cards)
            write_log("First listing title", first_title or "매물을 찾지 못했습니다", page.url, condition)
            write_log("First listing price", first_price or "가격을 찾지 못했습니다", page.url, condition)
            new_count, duplicate_count, price_changed_count, limit_skipped_count = save_candidate_cards(
                cards, page.url, condition
            )
            export_csv()
            write_log("Actual listings saved", str(new_count), page.url, condition)
            write_log("New listings saved", str(new_count), page.url, condition)
            write_log("Duplicate skipped", str(duplicate_count), page.url, condition)
            write_log("Price changes detected", str(price_changed_count), page.url, condition)
            write_log("Save limit skipped", str(limit_skipped_count), page.url, condition)
            write_log("Saved count", str(new_count), page.url, condition)
            write_log("중복 제외 개수", str(duplicate_count), page.url, condition)
            # Exiting sync_playwright disconnects CDP. It does not close the user's Chrome.
    except Exception as error:
        message = FAILURE_MESSAGE if "connect_over_cdp" in str(error) else str(error)
        if not message:
            message = FAILURE_MESSAGE
        write_log("Collection failed", message, condition=condition)
        print(FAILURE_MESSAGE if message == FAILURE_MESSAGE else message)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
