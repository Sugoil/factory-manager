# -*- coding: utf-8 -*-
"""Collect visible listings from a user-opened Chrome tab through CDP."""

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from db_store import add_log, insert_listing, load_conditions, load_listings, replace_listings


ROOT = Path(__file__).resolve().parent
CDP_URL = "http://localhost:9222"
LISTINGS_FILE = ROOT / "listings.csv"
LOG_FILE = ROOT / "collect_logs.csv"
MAX_NEW = 3
LAND_HOSTS = ("land.naver.com", "new.land.naver.com", "fin.land.naver.com")
REJECTED_PATHS = ("/news", "/404", "headline")
FAILURE_MESSAGE = (
    "start_chrome_debug.bat을 먼저 실행하고, "
    "네이버부동산에서 검색 결과 화면을 열어주세요."
)
BLOCKED_TEXTS = ("captcha", "비정상적인 접근", "접근이 제한", "요청이 너무 많")
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
    if "월세" in text or re.search(r"\d[\d,]*\s*/\s*\d[\d,]*", text):
        return "월세"
    if "전세" in text:
        return "전세"
    if "매매" in text:
        return "매매"
    return "기타"


def price_fields(text, deal_type):
    slash = re.search(r"(\d[\d,]*)\s*/\s*(\d[\d,]*)", text)
    labeled = re.search(r"(?:매매|전세|가격)\s*([\d,.]+\s*억(?:\s*[\d,.]+)?|[\d,.]+)", text)
    price = parse_price(labeled.group(1)) if labeled else 0
    return {
        "매매가(만원)": price if deal_type == "매매" else 0,
        "전세금(만원)": price if deal_type == "전세" else 0,
        "보증금(만원)": parse_price(slash.group(1)) if slash else 0,
        "월세(만원)": parse_price(slash.group(2)) if slash else 0,
    }


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


def card_to_row(card, page_url, condition):
    text = re.sub(r"\s+", " ", str(card.get("text", ""))).strip()
    url = str(card.get("url", "")).strip()
    aid = str(card.get("articleNo", "")).strip() or article_id(url)
    lines = listing_lines(card)
    deal_type = detect_deal_type(text)
    area_match = re.search(r"([\d,.]+)\s*(?:㎡|m2|m²|평)", text, re.IGNORECASE)
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
        "전용면적(㎡)": parse_number(area_match.group(1)) if area_match else 0,
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
    }
    row.update(price_fields(text, deal_type))
    return row


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
        if not str(item.get("지역", "")).strip():
            item["지역"] = "청주시"
        cleaned.append(item)
    removed = len(rows) - len(cleaned)
    if removed or cleaned != rows:
        replace_listings(cleaned)
        export_csv()
    return removed


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
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with LISTINGS_FILE.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright가 설치되어 있지 않습니다.")
        print("python -m pip install -r requirements.txt")
        return 2

    conditions = [item for item in load_conditions() if item.get("enabled", True)]
    condition = conditions[0] if conditions else {}
    write_log("실행 시간", now(), condition=condition)
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
            excluded_count = len(candidate_cards) - len(cards)
            write_log("Candidate cards found", str(len(candidate_cards)), page.url, condition)
            write_log("Excluded UI items", str(excluded_count), page.url, condition)
            write_log("Listing cards found", str(len(cards)), page.url, condition)
            first_title, first_price = first_listing_summary(cards)
            write_log("First listing title", first_title or "매물을 찾지 못했습니다", page.url, condition)
            write_log("First listing price", first_price or "가격을 찾지 못했습니다", page.url, condition)
            for card in cards[:MAX_NEW]:
                if insert_listing(card_to_row(card, page.url, condition)):
                    new_count += 1
                else:
                    duplicate_count += 1
            export_csv()
            write_log("Actual listings saved", str(new_count), page.url, condition)
            write_log("Saved count", str(new_count), page.url, condition)
            write_log("중복 제외 개수", str(duplicate_count), page.url, condition)
            # Exiting sync_playwright disconnects CDP. It does not close the user's Chrome.
    except Exception as error:
        message = FAILURE_MESSAGE if "connect_over_cdp" in str(error) else str(error)
        if not message:
            message = FAILURE_MESSAGE
        write_log("실패 사유", message, condition=condition)
        print(FAILURE_MESSAGE if message == FAILURE_MESSAGE else message)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
