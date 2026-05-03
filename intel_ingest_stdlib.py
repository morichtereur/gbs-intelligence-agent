# intel_ingest_stdlib.py — Mac M4 compatible (TLCA v3)
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from urllib.parse import parse_qs, urlparse, unquote, urlunparse, urlencode

import requests
import xml.etree.ElementTree as ET

DB_PATH = os.getenv("INTEL_DB_PATH", "intel.db")
SOURCES_PATH = os.getenv("INTEL_SOURCES_PATH", "sources.json")

VERIFY_SSL = os.getenv("INTEL_VERIFY_SSL", "1").strip() not in ("0", "false", "False")
ALLOW_INSECURE_SSL_FALLBACK = os.getenv("ALLOW_INSECURE_SSL_FALLBACK", "1") == "1"
HTTP_TIMEOUT = int(os.getenv("INTEL_HTTP_TIMEOUT", "25"))

DEDUP_ON_CANONICAL = os.getenv("INTEL_DEDUP_ON_CANONICAL", "1").strip() not in ("0", "false", "False")

ALLOWED_TAGS = [
    t.strip()
    for t in os.getenv("INTEL_ALLOWED_TAGS", "GBS,GCC,Agentic_AI,Operating_Model,Client_Signal").split(",")
    if t.strip()
]
REQUIRE_TAG_MATCH = os.getenv("INTEL_REQUIRE_TAG_MATCH", "1").strip() not in ("0", "false", "False")

EXCLUDE_URL_REGEX = os.getenv(
    "INTEL_EXCLUDE_URL_REGEX",
    r"(?i)("
    r"/careers\b|/career\b|/jobs\b|/job\b|/vacanc|/vacature|/apply\b|/talent\b|/join-us\b|/joinus\b|"
    r"/people\b|/person\b|/leadership\b|/leadership-team\b|/team\b|/bio\b|/biography\b|/profile\b|/profiles\b|"
    r"linkedin\.com/|glassdoor\.|indeed\.|myworkdayjobs\.|successfactors\.|smartrecruiters\.|greenhouse\.|lever\.|"
    r"icims\.|eightfold\.|workable\.|jobvite\.|recruitee\."
    r")"
).strip()

EXCLUDE_TITLE_REGEX = os.getenv(
    "INTEL_EXCLUDE_TITLE_REGEX",
    r"(?i)("
    r"\bpartner\b|\bprincipal\b|\bmanaging director\b|\bassociate director\b|\bdirector\b|\bsenior manager\b|"
    r"\bprofile\b|\bbio\b|\bbiography\b|\bmeet\b|\bpeople\b|\bleadership\b|"
    r"\bjob\b|\bjobs\b|\bcareer\b|\bcareers\b|\bvakan|\bvacanc|\bvacature\b|\bapply\b|\bhiring\b"
    r")"
).strip()

EXCLUDE_URL_RE = re.compile(EXCLUDE_URL_REGEX) if EXCLUDE_URL_REGEX else None
EXCLUDE_TITLE_RE = re.compile(EXCLUDE_TITLE_REGEX) if EXCLUDE_TITLE_REGEX else None


@dataclass
class FeedSource:
    source: str
    url: str


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean_html(text: str) -> str:
    if not text:
        return ""
    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def unwrap_google_redirect(url: str) -> str:
    try:
        u = urlparse(url or "")
        if "google." in (u.netloc or "") and u.path == "/url":
            qs = parse_qs(u.query)
            for key in ("url", "q"):
                if key in qs and qs[key]:
                    return unquote(qs[key][0])
    except Exception:
        pass
    return (url or "").strip()


def upgrade_http_to_https(url: str) -> str:
    u = (url or "").strip()
    if u.lower().startswith("http://"):
        return "https://" + u[7:]
    return u


def strip_tracking_params(url: str) -> str:
    try:
        p = urlparse(url)
        qs = parse_qs(p.query, keep_blank_values=True)
        drop_prefixes = ("utm_",)
        drop_keys = {
            "gclid", "fbclid", "mc_cid", "mc_eid", "igshid", "mkt_tok",
            "ref", "ref_", "cmpid", "cmp", "source", "smid"
        }
        new_qs = {}
        for k, v in qs.items():
            kl = k.lower()
            if any(kl.startswith(pref) for pref in drop_prefixes):
                continue
            if kl in drop_keys:
                continue
            new_qs[k] = v
        new_query = urlencode(new_qs, doseq=True)
        p2 = p._replace(query=new_query, fragment="")
        return urlunparse(p2)
    except Exception:
        return url


def normalize_url(url: str) -> str:
    u = (url or "").strip()
    u = unwrap_google_redirect(u)
    u = upgrade_http_to_https(u)
    u = strip_tracking_params(u)
    return u.strip()


def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()


def connect_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=30)
    try:
        con.execute("PRAGMA busy_timeout = 30000")
    except Exception:
        pass
    try:
        con.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    return con


def _add_col_if_missing(cur: sqlite3.Cursor, table: str, col_name: str, col_type: str) -> None:
    try:
        cur.execute(f"PRAGMA table_info({table})")
        cols = {r[1] for r in cur.fetchall()}
        if col_name not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
    except Exception:
        pass


def ensure_schema(con: sqlite3.Connection) -> None:
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS articles (
            article_id TEXT PRIMARY KEY,
            source TEXT,
            title TEXT,
            url TEXT,
            published_at TEXT,
            created_at TEXT,
            snippet TEXT,
            tags TEXT
        )
        """
    )
    _add_col_if_missing(cur, "articles", "clean_url", "TEXT")
    _add_col_if_missing(cur, "articles", "feed_type", "TEXT")  # 'competitor' or 'client'

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS article_summaries (
            article_id TEXT PRIMARY KEY,
            bullets TEXT,
            created_at TEXT
        )
        """
    )

    cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_created_at ON articles(created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source)")
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_clean_url ON articles(clean_url)")
    except Exception:
        pass
    con.commit()


def load_sources() -> tuple[list[FeedSource], dict[str, list[str]], list[str]]:
    with open(SOURCES_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    feeds = [FeedSource(**x) for x in cfg.get("feeds", [])]
    tag_rules = cfg.get("tag_rules", {})
    competitor_sources = cfg.get("competitor_sources", [])
    return feeds, tag_rules, competitor_sources


def infer_tags(text: str, tag_rules: dict[str, list[str]]) -> list[str]:
    t = (text or "").lower()
    found: list[str] = []
    for tag, keywords in tag_rules.items():
        if ALLOWED_TAGS and tag not in ALLOWED_TAGS:
            continue
        for kw in keywords:
            if kw.lower() in t:
                found.append(tag)
                break
    return found


def is_excluded(title: str, url: str) -> bool:
    t = (title or "").strip()
    u = (url or "").strip()
    if EXCLUDE_URL_RE and u and EXCLUDE_URL_RE.search(u):
        return True
    if EXCLUDE_TITLE_RE and t and EXCLUDE_TITLE_RE.search(t):
        return True
    return False


def get_feed_type(source: str, competitor_sources: list[str]) -> str:
    """Classify feed as 'competitor' or 'client' based on source name prefix."""
    for comp in competitor_sources:
        if source.startswith(comp):
            return "competitor"
    return "client"


def fetch_feed_xml(url: str) -> str:
    headers = {
        # Mac-friendly user agent
        "User-Agent": "competitor-intel/1.0 (+macOS; requests)",
        "Accept": "application/atom+xml, application/xml;q=0.9, */*;q=0.8",
    }

    def _do(verify: bool) -> str:
        r = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT, verify=verify)
        r.raise_for_status()
        return r.text

    try:
        return _do(VERIFY_SSL)
    except Exception as e1:
        if not ALLOW_INSECURE_SSL_FALLBACK or not VERIFY_SSL:
            raise e1
        return _do(False)


def parse_atom(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = []
    for e in root.findall("atom:entry", ns):
        title = (e.findtext("atom:title", default="", namespaces=ns) or "").strip()
        published = (e.findtext("atom:published", default="", namespaces=ns) or "").strip()
        summary = (e.findtext("atom:content", default="", namespaces=ns) or "").strip()
        link = ""
        link_el = e.find("atom:link", ns)
        if link_el is not None:
            link = (link_el.attrib.get("href", "") or "").strip()
        entries.append({"title": title, "link": link, "published": published, "summary": summary})
    return entries


def _has_column(con: sqlite3.Connection, table: str, col: str) -> bool:
    try:
        cur = con.cursor()
        cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
        return col in cols
    except Exception:
        return False


def upsert_article(
    con: sqlite3.Connection,
    source: str,
    title: str,
    url: str,
    published_at: str,
    snippet: str,
    tags: list[str],
    feed_type: str = "competitor",
) -> bool:
    cur = con.cursor()

    raw_url = (url or "").strip()
    clean_url = normalize_url(raw_url)

    if is_excluded(title, clean_url):
        return False

    if REQUIRE_TAG_MATCH and not tags:
        return False

    article_id = sha1(f"{source}|{clean_url}|{published_at}|{title}")
    created_at = now_utc_iso()

    if DEDUP_ON_CANONICAL:
        try:
            cur.execute(
                """
                SELECT 1 FROM articles
                WHERE source = ? AND COALESCE(clean_url,'') = ? AND COALESCE(published_at,'') = ?
                LIMIT 1
                """,
                (source, clean_url, published_at or ""),
            )
            if cur.fetchone() is not None:
                return False
        except Exception:
            pass

    cur.execute("SELECT 1 FROM articles WHERE article_id = ?", (article_id,))
    if cur.fetchone() is not None:
        return False

    cur.execute(
        """
        INSERT INTO articles(article_id, source, title, url, clean_url, published_at, created_at, snippet, tags, feed_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (article_id, source, title, raw_url, clean_url, published_at, created_at, snippet, ",".join(tags), feed_type),
    )

    con.commit()
    return True


def main() -> int:
    feeds, tag_rules, competitor_sources = load_sources()

    con = connect_db()
    try:
        ensure_schema(con)

        new_count = 0
        total_entries = 0
        skipped_excluded = 0
        skipped_notag = 0

        for feed in feeds:
            try:
                xml_text = fetch_feed_xml(feed.url)
                entries = parse_atom(xml_text)
                total_entries += len(entries)
                feed_type = get_feed_type(feed.source, competitor_sources)

                for ent in entries:
                    title = clean_html(ent.get("title", ""))
                    snippet = clean_html(ent.get("summary", ""))
                    raw_link = ent.get("link", "")
                    link = normalize_url(raw_link)
                    published = (ent.get("published", "") or "").strip()

                    if is_excluded(title, link):
                        skipped_excluded += 1
                        continue

                    tags = infer_tags(f"{title} {snippet}", tag_rules)

                    if REQUIRE_TAG_MATCH and not tags:
                        skipped_notag += 1
                        continue

                    if upsert_article(con, feed.source, title, link, published, snippet, tags, feed_type):
                        new_count += 1

            except Exception as ex:
                print(f"[WARN] Feed failed ({feed.source}): {ex}")

        print(
            f"Done. New: {new_count} | scanned: {total_entries} | "
            f"skipped excluded: {skipped_excluded} | skipped no-tag: {skipped_notag} | "
            f"allowed_tags: {ALLOWED_TAGS}"
        )
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
