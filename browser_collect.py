"""Low-volume Naver Real Estate collection from a visible Playwright browser."""

import csv
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from auto_collect import (
    CONDITIONS_FILE,
    LISTINGS_FILE,
    LOG_FILE,
    MAX_NEW,
    article_id,
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
PROFILE_DIR = ROOT / "playwright_profile"
BLOCKED_TEXTS = [
    "captcha", "자동입력 방지", "비정상적인 접근", "요청이 너무 많",
    "too many requests", "접근이 제한", "서비스 이용이 제한",
]
NAVER_MAIN_URL = "https://www.naver.com/"
AUTOMATION_BLOCKED_MESSAGE = (
    "네이버부동산이 자동 브라우저 접근을 제한하고 있습니다. "
    "수동 URL 저장 또는 텍스트 붙여넣기 방식을 사용해주세요."
)
REAL_ESTATE_LINK_TEXTS = ("네이버 부동산", "Npay 부동산", "N pay 부동산", "부동산 홈")
ALLOWED_LINK_HOSTS = ("land.naver.com", "new.land.naver.com", "fin.land.naver.com")
VALID_RESULT_HOSTS = ("land.naver.com", "new.land.naver.com")
BLOCKED_LINK_PARTS = ("financial.pstatic.net", "financial.naver.com", "pstatic.net/404")


class CollectionStepError(RuntimeError):
    def __init__(self, step, message):
        super().__init__(message)
        self.step = step


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


def launch_browser_context(playwright, condition):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    options = {
        "user_data_dir": str(PROFILE_DIR),
        "headless": False,
        "viewport": {"width": 1440, "height": 1000},
        "ignore_default_args": ["--no-sandbox"],
    }
    last_error = None
    for channel in ["chrome", "msedge", None]:
        channel_name = channel or "chromium"
        try:
            channel_options = dict(options)
            if channel:
                channel_options["channel"] = channel
            context = playwright.chromium.launch_persistent_context(**channel_options)
            log(condition, "Browser channel", channel_name)
            return context
        except Exception as error:
            last_error = error
            log(
                condition,
                "Browser channel failed",
                f"{channel_name}: {type(error).__name__}: {error}",
            )
    raise last_error


def page_is_blocked(page):
    try:
        text = page.locator("body").inner_text(timeout=5000).lower()
    except Exception:
        text = ""
    return any(item.lower() in text for item in BLOCKED_TEXTS)


def failure_log(condition, step, page, message):
    current_url = page.url if page else ""
    detail = f"Failed step: {step} | Current URL: {current_url} | {message}"
    log(condition, "Collection failed", detail, current_url)


def host_allowed(url, allowed_hosts):
    hostname = (urlparse(str(url)).hostname or "").lower()
    return any(hostname == host or hostname.endswith(f".{host}") for host in allowed_hosts)


def forbidden_link(url):
    lowered = str(url).lower()
    return any(part in lowered for part in BLOCKED_LINK_PARTS)


def link_priority(url):
    hostname = (urlparse(str(url)).hostname or "").lower()
    priorities = {
        "land.naver.com": 0,
        "new.land.naver.com": 1,
        "fin.land.naver.com": 2,
    }
    return priorities.get(hostname, 99)


def enter_naver_real_estate(context, page, condition):
    step = "Step 1: Open Naver"
    log(condition, step, NAVER_MAIN_URL, NAVER_MAIN_URL)
    page.goto(NAVER_MAIN_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)
    if page_is_blocked(page):
        raise CollectionStepError(step, "CAPTCHA 또는 요청 제한 화면 감지")

    step = "Step 2: Search Naver Real Estate"
    log(condition, step, "네이버 부동산", page.url)
    search_input = page.locator("input#query, input[name='query']").first
    search_input.wait_for(state="visible", timeout=15000)
    search_input.fill("네이버 부동산")
    search_input.press("Enter")
    page.wait_for_timeout(6000)
    if page_is_blocked(page):
        raise CollectionStepError(step, "CAPTCHA 또는 요청 제한 화면 감지")

    step = "Step 3: Click Real Estate Link"
    log(condition, step, "네이버 부동산 또는 N pay 부동산 링크 탐색", page.url)
    candidates = page.locator("a[href]")
    candidate_details = []
    for index in range(min(candidates.count(), 200)):
        candidate = candidates.nth(index)
        try:
            text = re.sub(r"\s+", " ", candidate.inner_text()).strip()
            href = str(candidate.get_attribute("href") or "").strip()
            if not text or not href or not candidate.is_visible():
                continue
            if not any(label in text for label in REAL_ESTATE_LINK_TEXTS):
                continue
            if forbidden_link(href) or not host_allowed(href, ALLOWED_LINK_HOSTS):
                continue
            candidate_details.append((candidate, text, href))
            print(f"Found link:\nText = {text}\nHref = {href}")
            log(condition, "Found link text", text, href)
            log(condition, "Found link href", href, href)
        except Exception:
            continue
    if not candidate_details:
        raise CollectionStepError(step, "허용된 부동산 도메인의 검색 결과 링크를 찾지 못했습니다.")
    candidate_details.sort(key=lambda item: link_priority(item[2]))

    for candidate, text, href in candidate_details:
        pages_before = list(context.pages)
        search_result_url = page.url
        try:
            candidate.click()
            page.wait_for_timeout(8000)
            new_pages = [item for item in context.pages if item not in pages_before]
            target_page = new_pages[-1] if new_pages else page
            target_page.wait_for_load_state("domcontentloaded", timeout=60000)
            target_page.wait_for_timeout(5000)
            current_url = target_page.url
            print(f"Clicked link:\nText = {text}")
            print(f"Clicked href:\n{href}")
            print(f"Current URL:\n{current_url}")
            log(condition, "Clicked link text", text, href)
            log(condition, "Clicked link href", href, href)
            log(condition, "Step 4: Current URL", current_url, current_url)
            if (
                host_allowed(current_url, VALID_RESULT_HOSTS)
                and not forbidden_link(current_url)
                and "/404" not in current_url
                and not page_is_blocked(target_page)
            ):
                log(condition, "Entered Naver Real Estate", current_url, current_url)
                return target_page
            log(
                condition,
                "Rejected clicked link",
                f"Text={text} | Href={href} | Current URL={current_url}",
                current_url,
            )
            if target_page is not page:
                target_page.close()
            elif page.url != search_result_url:
                page.go_back(wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000)
        except Exception as error:
            log(
                condition,
                "Link candidate failed",
                f"Text={text} | Href={href} | {type(error).__name__}: {error}",
                href,
            )
    raise CollectionStepError(step, "정상 네이버부동산 링크로 진입하지 못했습니다.")


def finish_browser(context):
    if os.environ.get("KEEP_BROWSER_OPEN") == "1":
        print("Browser inspection mode: close the browser window or press Enter to finish.")
        try:
            input("Press Enter to close...")
        except (EOFError, KeyboardInterrupt):
            print("Input wait was interrupted. The browser will remain open.")
            return
    try:
        context.close()
    except Exception:
        pass


def keep_browser_open_after_error(context, error):
    print(f"Collection error: {type(error).__name__}: {error}")
    if os.environ.get("KEEP_BROWSER_OPEN") == "1":
        print("The browser will remain open so you can inspect the current page.")
        try:
            input("Press Enter to close...")
        except (EOFError, KeyboardInterrupt):
            print("Input wait was interrupted. The browser will remain open.")
            return
    try:
        context.close()
    except Exception:
        pass


def region_search_text(condition):
    region = str((condition.get("regions") or ["충북 전체"])[0]).strip()
    aliases = {
        "충북 전체": "충청북도",
        "청주시 전체": "청주시",
        "청주": "청주시",
        "진천": "진천군",
        "음성": "음성군",
    }
    return aliases.get(region, region)


def perform_region_search(page, condition, playwright_timeout_error):
    query = region_search_text(condition)
    input_selectors = [
        "input[placeholder*='단지']",
        "input[placeholder*='지역']",
        "input[placeholder*='검색']",
        "input[type='text']",
        "input.search_input",
        ".search_input input",
        "input[type='search']",
    ]
    search_input = None
    search_scope = page
    found_selector = ""
    for scope in [page, *page.frames]:
        for selector in input_selectors:
            candidate = scope.locator(selector).first
            try:
                candidate.wait_for(state="visible", timeout=2000)
                search_input = candidate
                search_scope = scope
                found_selector = selector
                break
            except playwright_timeout_error:
                continue
        if search_input is not None:
            break
    if search_input is None:
        for scope in [page, *page.frames]:
            candidate = scope.get_by_role("textbox").first
            try:
                candidate.wait_for(state="visible", timeout=2000)
                search_input = candidate
                search_scope = scope
                found_selector = "role=textbox"
                break
            except playwright_timeout_error:
                continue
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
                    found_selector = selector
                    break
                except playwright_timeout_error:
                    continue
            if search_input is not None:
                break
    if search_input is None:
        input_details = []
        for frame_index, scope in enumerate([page, *page.frames]):
            inputs = scope.locator("input")
            for index in range(min(inputs.count(), 50)):
                candidate = inputs.nth(index)
                try:
                    input_details.append({
                        "frame": frame_index,
                        "type": candidate.get_attribute("type") or "",
                        "placeholder": candidate.get_attribute("placeholder") or "",
                        "aria_label": candidate.get_attribute("aria-label") or "",
                        "visible": candidate.is_visible(),
                    })
                except Exception as error:
                    input_details.append({"frame": frame_index, "error": str(error)})
        detail = json.dumps(input_details, ensure_ascii=False, default=str)
        print(f"Input elements: {detail}")
        log(condition, "Input elements and placeholders", detail, page.url)
        raise CollectionStepError(
            "Step 5: Search Region",
            "네이버부동산 내부 지역 검색창을 찾지 못했습니다.",
        )

    before_url = page.url
    print(f"Current URL before region search: {before_url}")
    log(condition, "Current URL before region search", before_url, before_url)
    print("Region search input found")
    print(f"Search input selector found: {found_selector}")
    log(condition, "Search input selector found", found_selector, before_url)
    print(f"Search query: {query}")
    log(condition, "Search query", query, before_url)
    search_input.click()
    page.wait_for_timeout(1000)
    try:
        search_input.fill("")
        search_input.type(query, delay=150)
    except Exception:
        search_input.fill(query)
    page.wait_for_timeout(1000)
    print(f"Search query typed: {query}")
    log(condition, "Search query typed", query, before_url)

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
            print("Suggestion clicked")
            log(condition, "Suggestion clicked", query, page.url)
            break
        except playwright_timeout_error:
            continue
    if not clicked:
        print("Suggestion not found. Pressing Enter.")
        log(condition, "Suggestion not found", query, page.url)
        search_input.press("Enter")
        log(condition, "Search input Enter pressed", query, page.url)

    page.wait_for_timeout(10000)
    if page.url == before_url:
        page.wait_for_timeout(5000)
    print(f"Current URL after region search: {page.url}")
    log(condition, "Current URL after region search", page.url, page.url)
    if "/404" in page.url:
        detail = f"검색어={query} | Current URL={page.url}"
        log(condition, "404 detected step", detail, page.url)
        raise CollectionStepError("Step 5: Search Region", detail)
    if page_is_blocked(page):
        raise CollectionStepError(
            "Step 5: Search Region",
            "CAPTCHA 또는 접근 제한 화면 감지",
        )
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
            const card = element.closest('li') || element.closest('article') ||
                         element.closest('[class*="item"]') || element.parentElement;
            const link = element.href ? element : card?.querySelector("a[href*='/articles/'], a[href*='articleNo=']");
            const url = link?.href || (articleNo ? `https://new.land.naver.com/articles/${articleNo}` : '');
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
    log(condition, "처리한 조건", json.dumps(condition, ensure_ascii=False, default=str))
    time.sleep(random.uniform(10, 30))

    new_count = 0
    duplicate_count = 0
    context = None
    page = None
    current_step = "Browser launch"
    try:
        with sync_playwright() as playwright:
            context = launch_browser_context(playwright, condition)
            page = context.pages[0] if context.pages else context.new_page()
            current_step = "Step 1-4: Enter Naver Real Estate"
            page = enter_naver_real_estate(context, page, condition)
            current_step = "Step 5: Search Region"
            log(condition, current_step, region_search_text(condition), page.url)
            search_query, search_result_url = perform_region_search(
                page, condition, PlaywrightTimeoutError
            )
            condition["search_url"] = search_result_url
            print(f"Search query: {search_query}")
            print(f"Search result URL: {search_result_url}")
            log(condition, "Step 5: Search Region", search_result_url, search_result_url)
            if "/404" in search_result_url:
                raise RuntimeError(AUTOMATION_BLOCKED_MESSAGE)
            visible_text = page.locator("body").inner_text(timeout=10000)
            if any(item.lower() in visible_text.lower() for item in BLOCKED_TEXTS):
                raise RuntimeError("CAPTCHA 또는 요청 제한 화면 감지")
            current_step = "Step 6: Listing Count"
            try:
                page.locator(
                    "a[href*='/articles/'], a[href*='articleNo='], [data-article-no], "
                    ".item_inner, .item_link, li[class*='item']"
                ).first.wait_for(
                    state="visible", timeout=30000
                )
            except PlaywrightTimeoutError:
                raise RuntimeError("화면에서 매물 카드를 찾지 못했습니다.")
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
            print(f"Step 6: Listing Count: {len(unique)}")
            log(condition, "Step 6: Listing Count", str(len(unique)), page.url)
            current_step = "Step 7: Saved Count"
            for card in list(unique.values())[:MAX_NEW]:
                row = card_to_row(card, condition)
                if insert_listing(row):
                    new_count += 1
                else:
                    duplicate_count += 1
            print(f"Step 7: Saved Count: {new_count}")
            log(condition, "Step 7: Saved Count", str(new_count), page.url)
            finish_browser(context)
            context = None
    except Exception as error:
        if isinstance(error, CollectionStepError):
            current_step = error.step
        message = f"{type(error).__name__}: {error}"
        if "Executable doesn't exist" in str(error):
            message += " | 최초 1회 실행: python -m playwright install chromium"
        failure_log(condition, current_step, page, message)
        if AUTOMATION_BLOCKED_MESSAGE in message:
            log(condition, "브라우저 자동화 수집 불가", AUTOMATION_BLOCKED_MESSAGE, page.url if page else "")
        if context is not None:
            keep_browser_open_after_error(context, error)
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
