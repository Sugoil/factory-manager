"""Shared SQLite storage for the Streamlit app and GitHub Actions collector."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from listing_normalizer import normalize_listing
from region_classifier import enrich_listing_region

DB_FILE = Path(__file__).with_name("listings.db")


@contextmanager
def connect(db_file=DB_FILE):
    connection = sqlite3.connect(db_file)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db(db_file=DB_FILE):
    with connect(db_file) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                naver_article_id TEXT,
                naver_url TEXT,
                duplicate_key TEXT,
                auto_collected TEXT,
                collected_at TEXT,
                data_json TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_listings_article
                ON listings(naver_article_id) WHERE naver_article_id != '';
            CREATE UNIQUE INDEX IF NOT EXISTS idx_listings_url
                ON listings(naver_url) WHERE naver_url != '';
            DROP INDEX IF EXISTS idx_listings_duplicate;
            CREATE UNIQUE INDEX idx_listings_duplicate
                ON listings(duplicate_key) WHERE duplicate_key != '';

            CREATE TABLE IF NOT EXISTS search_conditions (
                id TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                registered_at TEXT,
                last_collected_at TEXT,
                data_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS collect_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collected_at TEXT NOT NULL,
                condition_id TEXT,
                status TEXT,
                url TEXT,
                message TEXT
            );

            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                listing_id INTEGER NOT NULL,
                naver_article_id TEXT,
                naver_url TEXT,
                previous_price REAL NOT NULL,
                current_price REAL NOT NULL,
                price_change_amount REAL NOT NULL,
                price_changed_at TEXT NOT NULL
            );
            """
        )


def listing_identity(row):
    article_id = str(row.get("naver_article_id") or row.get("네이버 매물 ID", "")).strip()
    url = str(row.get("naver_url") or row.get("네이버부동산 링크", "")).strip()
    name = str(row.get("매물명", "")).strip()
    address = str(row.get("duplicate_address", row.get("주소", ""))).strip()
    price = row.get("매매가(만원)", 0) or row.get("전세금(만원)", 0) or 0
    area = row.get("전용면적(㎡)") or row.get("건물면적(㎡)") or row.get("대지면적(㎡)") or 0
    duplicate_key = (
        "|".join([name or address, str(price), str(area)])
        if (name or address) and (price or area)
        else ""
    )
    return article_id, url, duplicate_key


def listing_price(row):
    return float(
        row.get("매매가(만원)", 0)
        or row.get("전세금(만원)", 0)
        or row.get("월세(만원)", 0)
        or 0
    )


def upsert_collected_listing(row, db_file=DB_FILE):
    """Insert a listing or update its price when the same ID/URL already exists."""
    row = normalize_listing(enrich_listing_region(row))
    init_db(db_file)
    article_id, url, duplicate_key = listing_identity(row)
    with connect(db_file) as db:
        existing = None
        matched_by = ""
        if article_id:
            existing = db.execute(
                "SELECT id, data_json FROM listings WHERE naver_article_id = ?",
                (article_id,),
            ).fetchone()
            if existing is not None:
                matched_by = "article_id"
        if existing is None and url:
            existing = db.execute(
                "SELECT id, data_json FROM listings WHERE naver_url = ?",
                (url,),
            ).fetchone()
            if existing is not None:
                matched_by = "url"
        if existing is None and duplicate_key:
            existing = db.execute(
                "SELECT id, data_json FROM listings WHERE duplicate_key = ?",
                (duplicate_key,),
            ).fetchone()
            if existing is not None:
                matched_by = "duplicate_key"

        if existing is None:
            row["current_price"] = listing_price(row)
            row = normalize_listing(row)
            payload = json.dumps(row, ensure_ascii=False, default=str)
            db.execute(
                """
                INSERT INTO listings
                (naver_article_id, naver_url, duplicate_key, auto_collected, collected_at, data_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    article_id, url, duplicate_key, str(row.get("auto_collected", "")),
                    str(row.get("collected_at", "")), payload,
                ),
            )
            return "new"

        if matched_by == "duplicate_key":
            return "duplicate"

        old_row = json.loads(existing["data_json"])
        previous_price = listing_price(old_row)
        current_price = listing_price(row)
        updated = dict(old_row)
        updated.update(row)
        updated["first_seen_at"] = old_row.get("first_seen_at") or row.get("first_seen_at", "")
        updated["last_seen_at"] = row.get("last_seen_at") or datetime.now().isoformat(timespec="seconds")
        status = "duplicate"
        same_deal_type = old_row.get("거래유형") == row.get("거래유형")
        if same_deal_type and previous_price != current_price and previous_price > 0 and current_price > 0:
            changed_at = datetime.now().astimezone().isoformat(timespec="seconds")
            updated.update(
                {
                    "previous_price": previous_price,
                    "current_price": current_price,
                    "price_changed_at": changed_at,
                    "price_change_amount": current_price - previous_price,
                }
            )
            db.execute(
                """
                INSERT INTO price_history
                (listing_id, naver_article_id, naver_url, previous_price, current_price,
                 price_change_amount, price_changed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    existing["id"], article_id, url, previous_price, current_price,
                    current_price - previous_price, changed_at,
                ),
            )
            status = "price_changed"
        elif not same_deal_type:
            for key in ("previous_price", "current_price", "price_changed_at", "price_change_amount"):
                updated.pop(key, None)
        updated = normalize_listing(updated)
        db.execute(
            """
            UPDATE listings
            SET naver_article_id = ?, naver_url = ?, duplicate_key = ?,
                auto_collected = ?, collected_at = ?, data_json = ?
            WHERE id = ?
            """,
            (
                article_id, url, duplicate_key, str(updated.get("auto_collected", "")),
                str(updated.get("collected_at", "")),
                json.dumps(updated, ensure_ascii=False, default=str), existing["id"],
            ),
        )
        return status


def load_price_history(limit=100, db_file=DB_FILE):
    init_db(db_file)
    with connect(db_file) as db:
        rows = db.execute(
            """
            SELECT naver_article_id, naver_url, previous_price, current_price,
                   price_change_amount, price_changed_at
            FROM price_history ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def insert_listing(row, db_file=DB_FILE):
    init_db(db_file)
    row = normalize_listing(enrich_listing_region(row))
    article_id, url, duplicate_key = listing_identity(row)
    payload = json.dumps(row, ensure_ascii=False, default=str)
    try:
        with connect(db_file) as db:
            db.execute(
                """
                INSERT INTO listings
                (naver_article_id, naver_url, duplicate_key, auto_collected, collected_at, data_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    article_id, url, duplicate_key, str(row.get("auto_collected", "")),
                    str(row.get("collected_at", "")), payload,
                ),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def replace_listings(rows, db_file=DB_FILE):
    init_db(db_file)
    with connect(db_file) as db:
        db.execute("DELETE FROM listings")
    for row in rows:
        insert_listing(dict(row), db_file)


def load_listings(db_file=DB_FILE):
    init_db(db_file)
    with connect(db_file) as db:
        return [json.loads(row["data_json"]) for row in db.execute("SELECT data_json FROM listings ORDER BY id")]


def replace_conditions(conditions, db_file=DB_FILE):
    init_db(db_file)
    with connect(db_file) as db:
        db.execute("DELETE FROM search_conditions")
        for condition in conditions:
            item = dict(condition)
            condition_id = str(item.get("id") or datetime.now().strftime("%Y%m%d%H%M%S%f"))
            item["id"] = condition_id
            db.execute(
                """
                INSERT INTO search_conditions (id, enabled, registered_at, last_collected_at, data_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    condition_id, 1 if item.get("enabled", True) else 0,
                    str(item.get("registered_at", "")), str(item.get("last_collected_at", "")),
                    json.dumps(item, ensure_ascii=False, default=str),
                ),
            )


def load_conditions(db_file=DB_FILE):
    init_db(db_file)
    with connect(db_file) as db:
        return [json.loads(row["data_json"]) for row in db.execute(
            "SELECT data_json FROM search_conditions ORDER BY registered_at, id"
        )]


def add_log(condition_id="", status="", url="", message="", collected_at="", db_file=DB_FILE):
    init_db(db_file)
    collected_at = collected_at or datetime.now().isoformat(timespec="seconds")
    with connect(db_file) as db:
        db.execute(
            "INSERT INTO collect_logs (collected_at, condition_id, status, url, message) VALUES (?, ?, ?, ?, ?)",
            (collected_at, condition_id, status, url, message),
        )


def load_logs(limit=100, db_file=DB_FILE):
    init_db(db_file)
    with connect(db_file) as db:
        rows = db.execute(
            "SELECT collected_at, condition_id, status, url, message FROM collect_logs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
