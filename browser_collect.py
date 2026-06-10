"""Low-volume Naver Real Estate collection from a visible Playwright browser."""

import csv
import json
import random
import re
import sys
import time
from pathlib import Path

from auto_collect import (
    CONDITIONS_FILE,
    LISTINGS_FILE,
    LOG_FILE,
    MAX_NEW,
    article_id,
    build_search_url,
    normalize_condition,
    normalize_deal,
    normalize_type,
    now,
    parse_price,
)
from db_store import (
    add_log,
    insert_listing,
    load_conditions,
    load_listings,
    replace_conditions,
)


ROOT = Path(__file__).parent
PROFILE_DIR = ROOT / ".playwright-profile"
BLOCKED_TEXTS = [
    "captcha", "자동입력 방지", "비정상적인 접근", "요청이 너무 많",
    "too many requests", "접근이 제한", "서비스 이용이 제한",
]
NAVER_HOME_URL = "https://new.land.naver.com/"


def log(condition, status, message="", url=""):
    collected_at = now()
    condition_id = str(condition.get("id", "")) if condition else ""
    print(f"{status}: {message}")
    add_log(condition_id, status, url, message, collected_at)
    exists = LOG_FILE.exists()
    with LOG_FILE.open("a", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file, fieldnames=["수집시간", "조건ID", "상태", "URL", "메시지"]
        )
        if not exists:
            writer.writeheader()
        writer.writerow({
            "수집시간": collected_at, "조건ID": condition_id, "상태": status,
            "URL": url, "메시지": message,
        })


def read_conditions():
    conditions = load_conditions()
    if CONDITIONS_FILE.exists():
        try:
            conditions = json.loads(CONDITIONS_FILE.read_text(encoding="utf-8"))
            replace_conditions(conditions)
        except (json.JSONDecodeError, OSError) as error:
            log({}, "조건 읽기 실패", str(error))
    normalized = [normalize_condition(item) for item in conditions]
    selected = sorted(
        [item for item in normalized if item.get("enabled", True)],
        key=lambda item: item.get("last_collected_at", ""),
    )[:1]
    return selected, normalized


def browser_search_url(condition):
    """Always enter through Naver Land home and use its visible search UI."""
    return build_search_url(condition)


def region_search_text(condition):
    region = str((condition.get("regions") or ["충북 전체"])[0]).strip()
    aliases = {
        "충북 전체": "충북",
        "청주시 전체": "충북 청주시",
    }
    return aliases.get(region, region)


def perform_region_search(page, condition, playwright_timeout_error):
    query = region_search_text(condition)
    input_selectors = [
        "input[placeholder*='지역']",
        "input[placeholder*='단지']",
        "input[placeholder*='검색']",
        "input.search_input",
        ".search_input input",
        "input[type='search']",
    ]
    search_input = None
    search_scope = page
    for scope in [page, *page.frames]:
        for selector in input_selectors:
            candidate = scope.locator(selector).first
            try:
                candidate.wait_for(state="visible", timeout=2000)
                search_input = candidate
                search_scope = scope
                break
            except playwright_timeout_error:
                continue
        if search_input is not None:
            break
    if search_input is None:
        for selector in [
            "button[aria-label*='검색']",
            "button[class*='search']",
            "a[class*='search']",
            "button:has-text('검색')",
        ]:
            button = page.locator(selector).first
            try:
                button.wait_for(state="visible", timeout=1000)
                button.click()
                page.wait_for_timeout(1000)
                break
            except playwright_timeout_error:
                continue
        for scope in [page, *page.frames]:
            for selector in input_selectors:
                candidate = scope.locator(selector).first
                try:
                    candidate.wait_for(state="visible", timeout=1500)
                    search_input = candidate
                    search_scope = scope
                    break
                except playwright_timeout_error:
                    continue
            if search_input is not None:
                break
    if search_input is None:
        raise RuntimeError("네이버부동산 홈에서 지역 검색창을 찾지 못했습니다.")

    before_url = page.url
    search_input.click()
    search_input.fill(query)
    page.wait_for_timeout(1500)

    suggestion_selectors = [
        "[role='listbox'] [role='option']",
        ".search_result_list li",
        ".autocomplete_list li",
        ".search_list li",
        "ul[class*='search'] li",
    ]
    clicked = False
    for selector in suggestion_selectors:
        suggestion = search_scope.locator(selector).first
        try:
            suggestion.wait_for(state="visible", timeout=1500)
            suggestion.click()
            clicked = True
            break
        except playwright_timeout_error:
            continue
    if not clicked:
        search_input.press("Enter")

    page.wait_for_timeout(10000)
    if page.url == before_url:
        page.wait_for_timeout(5000)
    return query, page.url


def update_condition_snapshot(all_conditions, current):
    current_id = str(current.get("id", ""))
    for index, item in enumerate(all_conditions):
        if str(item.get("id", "")) == current_id:
            all_conditions[index] = dict(current)
            return


def price_fields(text, deal_type):
    slash = re.search(r"(?:월세|보증금)?\s*([\d,.억천만]+)\s*/\s*([\d,.억천만]+)", text)
    price_match = re.search(
        r"(?:매매|전세|월세|가격)\s*[:：]?\s*([\d,.억천만\s]+)", text
    )
    price = parse_price(price_match.group(1)) if price_match else 0
    deposit = parse_price(slash.group(1)) if slash else 0
    rent = parse_price(slash.group(2)) if slash else 0
    return {
        "매매가(만원)": price if deal_type == "매매" else 0,
        "전세금(만원)": price if deal_type == "전세" else 0,
        "보증금(만원)": deposit if deal_type == "월세" else 0,
        "월세(만원)": rent if deal_type == "월세" else 0,
    }


def card_to_row(card, condition):
    text = re.sub(r"\s+", " ", str(card.get("text", ""))).strip()
    url = str(card.get("url", "")).strip()
    aid = article_id(url)
    property_type = normalize_type(text)
    deal_type = normalize_deal(text)
    area_match = re.search(r"([\d,.]+)\s*㎡", text)
    floor_match = re.search(r"((?:지하\s*)?\d+층|\d+/\d+층)", text)
    agency_match = re.search(r"([가-힣A-Za-z0-9 ]+(?:공인중개사사무소|부동산))", text)
    verified_match = re.search(r"(확인매물|확인\s*\d{2}[./-]\d{2}[./-]\d{2})", text)
    date_match = re.search(r"\b(\d{2,4}[./-]\d{1,2}[./-]\d{1,2})\b", text)
    row = {
        "매물명": text[:80] or f"{property_type} 브라우저 자동수집",
        "주소": ", ".join(condition.get("regions", [])),
        "지역": ", ".join(condition.get("regions", [])),
        "매물종류": property_type, "거래유형": deal_type,
        "전용면적(㎡)": parse_price(area_match.group(1)) if area_match else 0,
        "층수": floor_match.group(1) if floor_match else "",
        "네이버부동산 링크": url, "네이버 매물 ID": aid,
        "naver_url": url, "naver_article_id": aid,
        "provider_agency_name": agency_match.group(1).strip() if agency_match else "",
        "agency_name": agency_match.group(1).strip() if agency_match else "",
        "is_verified_listing": "확인매물" if verified_match else "",
        "verified_date": date_match.group(1) if date_match else "",
        "platform": "네이버부동산", "auto_collected": "예",
        "collected_at": now(), "first_seen_at": now(), "last_seen_at": now(),
        "source_search_url": condition.get("search_url", ""),
        "collection_condition": json.dumps(condition, ensure_ascii=False, default=str),
        "extraction_status": "Playwright 화면 자동수집", "extraction_error": "",
        "매물 상태": "신규",
    }
    row.update(price_fields(text, deal_type))
    return row


def export_csv():
    rows = load_listings()
    if not rows:
        return
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with LISTINGS_FILE.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def collect_visible_cards(page):
    selector = (
        "a[href*='/articles/'], a[href*='articleNo='], [data-article-no], "
        ".item_inner, .item_link, li[class*='item']"
    )
    return page.locator(selector).evaluate_all(
        """
        elements => elements
          .filter(element => {
            const rect = element.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
          })
          .map(element => {
            const articleNo = element.dataset?.articleNo || '';
            const url = element.href || (articleNo ? `https://new.land.naver.com/articles/${articleNo}` : '');
            const card = element.closest('li') || element.closest('article') ||
                         element.closest('[class*="item"]') || element.parentElement;
            return {url, text: (card?.innerText || element.innerText || '').trim()};
          })
        """
    )


def first_card_summary(cards):
    for card in cards:
        text = re.sub(r"\s+", " ", str(card.get("text", ""))).strip()
        if not text:
            continue
        lines = [line.strip() for line in str(card.get("text", "")).splitlines() if line.strip()]
        title = lines[0] if lines else text[:80]
        price_match = re.search(
            r"(?:매매|전세|월세)\s*[\d,.억천만\s/]+|[\d,.]+\s*억(?:\s*[\d,.]+\s*천)?",
            text,
        )
        price = price_match.group(0).strip() if price_match else "가격 확인 필요"
        return title, price
    return "", ""


def main():
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright가 설치되어 있지 않습니다.")
        print("다음 명령을 최초 1회 실행해주세요:")
        print("python -m pip install -r requirements.txt")
        print("python -m playwright install chromium")
        return 2

    conditions, all_conditions = read_conditions()
    log({}, "실행 시간", now())
    log({}, "읽은 조건 개수", str(len(conditions)))
    if not conditions:
        log({}, "브라우저 수집 완료", "활성 자동수집 조건이 없습니다.")
        return 0

    condition = conditions[0]
    condition["last_collected_at"] = now()
    entry_url = browser_search_url(condition)
    log(condition, "처리한 조건", json.dumps(condition, ensure_ascii=False, default=str))
    original_condition = json.dumps(condition, ensure_ascii=False, default=str)
    log(condition, "Browser entry URL", entry_url, entry_url)
    time.sleep(random.uniform(10, 30))

    new_count = 0
    duplicate_count = 0
    try:
        with sync_playwright() as playwright:
            try:
                context = playwright.chromium.launch_persistent_context(
                    str(PROFILE_DIR), channel="chrome", headless=False,
                    viewport={"width": 1440, "height": 1000},
                )
            except Exception:
                context = playwright.chromium.launch_persistent_context(
                    str(PROFILE_DIR), headless=False,
                    viewport={"width": 1440, "height": 1000},
                )
            page = context.pages[0] if context.pages else context.new_page()
            browser_goto_url = NAVER_HOME_URL
            print(f"Browser goto URL: {browser_goto_url}")
            log(condition, "Browser goto URL", browser_goto_url, browser_goto_url)
            navigation_response = page.goto(
                browser_goto_url, wait_until="domcontentloaded", timeout=60000
            )
            page.wait_for_timeout(10000)
            current_url = page.url
            print(f"Current URL after load: {current_url}")
            log(condition, "Current URL after load", current_url, current_url)
            response_status = navigation_response.status if navigation_response else 0
            if "/404" in current_url or response_status == 404:
                print(f"Original condition: {original_condition}")
                print(f"Browser goto URL: {browser_goto_url}")
                print(f"Current URL: {current_url}")
                print("404 detected")
                log(
                    condition,
                    "404 detected",
                    (
                        f"Original condition: {original_condition} | "
                        f"Browser goto URL: {browser_goto_url} | "
                        f"Current URL: {current_url} | "
                        f"Status Code: {response_status}"
                    ),
                    current_url,
                )
                context.close()
                return 0

            search_query, search_result_url = perform_region_search(
                page, condition, PlaywrightTimeoutError
            )
            condition["search_url"] = search_result_url
            print(f"Search query: {search_query}")
            print(f"Search result URL: {search_result_url}")
            log(condition, "Search query", search_query)
            log(condition, "Search result URL", search_result_url, search_result_url)
            if "/404" in search_result_url:
                log(
                    condition,
                    "404 detected after search",
                    (
                        f"Original condition: {original_condition} | "
                        f"Browser goto URL: {browser_goto_url} | "
                        f"Current URL: {search_result_url}"
                    ),
                    search_result_url,
                )
                context.close()
                return 0
            visible_text = page.locator("body").inner_text(timeout=10000)
            if any(item.lower() in visible_text.lower() for item in BLOCKED_TEXTS):
                log(condition, "브라우저 수집 중단", "CAPTCHA 또는 요청 제한 화면 감지", page.url)
                context.close()
                return 0
            try:
                page.locator(
                    "a[href*='/articles/'], a[href*='articleNo='], [data-article-no], "
                    ".item_inner, .item_link, li[class*='item']"
                ).first.wait_for(
                    state="visible", timeout=30000
                )
            except PlaywrightTimeoutError:
                log(condition, "브라우저 수집 실패", "화면에서 매물 카드를 찾지 못했습니다.", page.url)
                context.close()
                return 0
            cards = collect_visible_cards(page)
            first_title, first_price = first_card_summary(cards)
            if first_title:
                print(f"First listing title: {first_title}")
                print(f"First listing price: {first_price}")
                log(condition, "First listing title", first_title, page.url)
                log(condition, "First listing price", first_price, page.url)
            unique = {}
            for card in cards:
                aid = article_id(card.get("url", ""))
                if aid:
                    unique[aid] = card
            log(condition, "화면 매물 개수", str(len(unique)), page.url)
            for card in list(unique.values())[:MAX_NEW]:
                row = card_to_row(card, condition)
                if insert_listing(row):
                    new_count += 1
                else:
                    duplicate_count += 1
            context.close()
    except Exception as error:
        message = f"{type(error).__name__}: {error}"
        if "Executable doesn't exist" in str(error):
            message += " | 최초 1회 실행: python -m playwright install chromium"
        log(condition, "브라우저 수집 실패", message, entry_url)
        return 1
    finally:
        condition["new_listing_count"] = new_count
        update_condition_snapshot(all_conditions, condition)
        replace_conditions(all_conditions)
        export_csv()

    log(condition, "신규 저장 개수", str(new_count))
    log(condition, "중복 제외 개수", str(duplicate_count))
    log(condition, "브라우저 수집 완료", f"신규 {new_count}개, 중복 {duplicate_count}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
