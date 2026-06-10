"""Shared SQLite storage for the Streamlit app and GitHub Actions collector."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


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
            """
        )


def listing_identity(row):
    article_id = str(row.get("naver_article_id") or row.get("네이버 매물 ID", "")).strip()
    url = str(row.get("naver_url") or row.get("네이버부동산 링크", "")).strip()
    address = str(row.get("duplicate_address", row.get("주소", ""))).strip()
    price = row.get("매매가(만원)", 0) or row.get("전세금(만원)", 0) or 0
    area = row.get("전용면적(㎡)") or row.get("건물면적(㎡)") or row.get("대지면적(㎡)") or 0
    duplicate_key = "|".join([address, str(price), str(area)]) if address or price or area else ""
    return article_id, url, duplicate_key


def insert_listing(row, db_file=DB_FILE):
    init_db(db_file)
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
