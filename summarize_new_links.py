# summarize_new_links.py — Claude API edition (TLCA v4 — with relevance scoring)
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import requests

# --- Config ---
ENABLE_LLM = os.getenv("ENABLE_LLM", "1").strip().lower() not in ("0", "false")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001").strip()
CLAUDE_TIMEOUT_SECONDS = int(os.getenv("CLAUDE_TIMEOUT_SECONDS", "45"))

DB_PATH = os.getenv("INTEL_DB_PATH", "intel.db")
WINDOW_DAYS = int((os.getenv("INTEL_WINDOW_DAYS", "7") or "7").strip())
MAX_TO_SUMMARIZE = int((os.getenv("INTEL_MAX_SUMMARIZE", "30") or "30").strip())

# Minimum relevance score to include in newsletter (1-3). Explorer shows all scores >= 1.
NEWSLETTER_MIN_SCORE = int(os.getenv("INTEL_MIN_SCORE", "3"))

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
CLAUDE_MAX_RETRIES = int(os.getenv("CLAUDE_MAX_RETRIES", "3"))

# Who the newsletter is for — used to frame the relevance-scoring prompt.
BRAND_CONTEXT = os.getenv(
    "INTEL_BRAND_CONTEXT",
    "a GBS / finance transformation consulting team",
).strip()


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def start_utc_iso(days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.replace(microsecond=0).isoformat()


def clamp_text(s: str, max_chars: int) -> str:
    s = (s or "").strip()
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1].rstrip() + "…"


def _build_prompt(title: str, url: str, snippet: str, feed_type: str) -> str:
    context_hint = (
        "This is a CLIENT signal — a publication, announcement, or market move by a company "
        "that is or could be a consulting client. Frame the summary from an advisory lens: "
        "what does this signal about their strategic direction, challenges, or transformation agenda? "
        "Do NOT start your response with CLIENT SIGNAL or any label prefix. "
        "If the article is primarily about a different company and the target company is only mentioned in passing, respond exactly: SKIP"
        if feed_type == "client"
        else "This is a COMPETITOR signal — a publication or market move by a consulting firm (MBB / Big4 / Accenture)."
    )

    return f"""You are producing a weekly competitor intelligence newsletter for {BRAND_CONTEXT}.
{context_hint}

First, rate the strategic relevance of this article for a GBS/finance transformation consultant on a scale of 1-3:
- Score 3 (HIGH): Direct strategic signal — new service offering, major client win, GBS/AI/operating model publication, C-suite move, M&A, or transformation announcement
- Score 2 (MEDIUM): Indirect signal — market commentary, industry trend piece, or tangentially relevant thought leadership
- Score 1 (LOW): Weak signal — generic news, product update with no strategic angle, or only marginally relevant

If any of the following apply, respond exactly: SKIP
- Job posting, person profile, or leadership bio
- Stock price movement, ETF holdings, or fund activity
- Insider trading filing or share sale notification
- Economic indicator report (e.g. PMI index, CPI, GDP data)
- Analyst valuation commentary with no strategic signal
- Routine earnings beat with no transformation angle

Otherwise respond in this exact format (no extra text):
SCORE: [1, 2, or 3]
SUMMARY: [2-3 sentences, max 60 words, factual, no hype]

Title: {title}
URL: {url}
Snippet: {snippet}
""".strip()


def _call_claude(prompt: str) -> str:
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 300,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }
    import time

    for attempt in range(1, CLAUDE_MAX_RETRIES + 1):
        try:
            resp = requests.post(ANTHROPIC_API_URL, headers=headers, json=payload, timeout=CLAUDE_TIMEOUT_SECONDS)
            # Retry on rate limits and transient server errors.
            if resp.status_code in (429, 500, 502, 503, 529) and attempt < CLAUDE_MAX_RETRIES:
                wait = 2 ** attempt
                sys.stderr.write(f"[WARN] Claude API {resp.status_code}, retrying in {wait}s ({attempt}/{CLAUDE_MAX_RETRIES})\n")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            text_out = ""
            for block in data.get("content", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    text_out += block.get("text", "")
            return text_out.strip()
        except Exception as e:
            if attempt < CLAUDE_MAX_RETRIES:
                wait = 2 ** attempt
                sys.stderr.write(f"[WARN] Claude API failed ({e}), retrying in {wait}s ({attempt}/{CLAUDE_MAX_RETRIES})\n")
                time.sleep(wait)
                continue
            sys.stderr.write(f"[WARN] Claude API failed after {CLAUDE_MAX_RETRIES} attempts: {e}\n")
    return ""


def parse_response(raw: str) -> tuple[int, str]:
    """
    Parse Claude response into (score, summary).
    Returns (0, 'SKIP') for skip, (score, summary) for valid responses.
    """
    if not raw:
        return 0, ""

    if raw.strip().upper() == "SKIP":
        return 0, "SKIP"

    score = 0
    summary = ""

    for line in raw.split("\n"):
        line = line.strip()
        if line.upper().startswith("SCORE:"):
            try:
                score = int(line.split(":", 1)[1].strip())
                score = max(1, min(3, score))  # clamp to 1-3
            except ValueError:
                score = 1
        elif line.upper().startswith("SUMMARY:"):
            summary = line.split(":", 1)[1].strip()
        elif summary and line:
            # continuation of summary
            summary += " " + line

    # Fallback: if no structured format, treat whole response as summary with score 2
    if not summary and raw and raw.upper() != "SKIP":
        summary = raw
        score = score or 2

    return score, clamp_text(summary, 600)


def llm_summarize(title: str, url: str, snippet: str, feed_type: str = "competitor") -> tuple[int, str]:
    """Returns (score, summary). Score 0 = SKIP."""
    if (not ENABLE_LLM) or (not ANTHROPIC_API_KEY):
        base = clamp_text(snippet or "", 420)
        return 2, base if base else "No AI summary available. Please open the link for details."

    prompt = _build_prompt(title, url, snippet, feed_type)
    raw = _call_claude(prompt)

    if not raw:
        return 0, ""

    if raw.strip().upper() == "SKIP":
        return 0, "SKIP"

    return parse_response(raw)


def ensure_score_column(con: sqlite3.Connection) -> None:
    """Add relevance_score column if missing."""
    try:
        cur = con.cursor()
        cols = [r[1] for r in cur.execute("PRAGMA table_info(article_summaries)").fetchall()]
        if "relevance_score" not in cols:
            cur.execute("ALTER TABLE article_summaries ADD COLUMN relevance_score INTEGER DEFAULT 2")
            con.commit()
            print("[info] Added relevance_score column to article_summaries")
    except Exception as e:
        sys.stderr.write(f"[WARN] Could not add score column: {e}\n")


def main() -> int:
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.cursor()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS article_summaries (
                article_id TEXT PRIMARY KEY,
                bullets TEXT,
                created_at TEXT,
                relevance_score INTEGER DEFAULT 2
            )
            """
        )
        con.commit()
        ensure_score_column(con)

        start_iso = start_utc_iso(WINDOW_DAYS)

        cur.execute(
            """
            SELECT a.article_id,
                   COALESCE(a.title, ''),
                   COALESCE(a.clean_url, a.url, ''),
                   COALESCE(a.snippet, ''),
                   COALESCE(a.feed_type, 'competitor')
            FROM articles a
            LEFT JOIN article_summaries s ON s.article_id = a.article_id
            WHERE a.created_at >= ?
              AND s.article_id IS NULL
            ORDER BY a.created_at DESC
            LIMIT ?
            """,
            (start_iso, MAX_TO_SUMMARIZE),
        )
        rows = cur.fetchall()

        print(f"[info] To summarize (window last {WINDOW_DAYS}d): {len(rows)}")

        saved = 0
        skipped = 0
        score_dist = {1: 0, 2: 0, 3: 0}

        for article_id, title, url, snippet, feed_type in rows:
            try:
                score, summary = llm_summarize(title=title, url=url, snippet=snippet, feed_type=feed_type)

                if score == 0 or summary.upper() == "SKIP":
                    cur.execute(
                        "INSERT OR REPLACE INTO article_summaries(article_id, bullets, relevance_score, created_at) VALUES (?,?,?,?)",
                        (article_id, "", 0, now_utc_iso()),
                    )
                    con.commit()
                    skipped += 1
                    continue

                cur.execute(
                    "INSERT OR REPLACE INTO article_summaries(article_id, bullets, relevance_score, created_at) VALUES (?,?,?,?)",
                    (article_id, summary, score, now_utc_iso()),
                )
                con.commit()
                saved += 1
                if score in score_dist:
                    score_dist[score] += 1

            except Exception as e:
                sys.stderr.write(f"[WARN] summarize failed: {title} | {e}\n")

        newsletter_count = score_dist.get(3, 0)
        print(f"[OK] Saved: {saved} | skipped: {skipped} | scores: 1={score_dist[1]} 2={score_dist[2]} 3={score_dist[3]}")
        print(f"[OK] Newsletter-ready (score=3): {newsletter_count} | Explorer-only (score 1-2): {score_dist[1] + score_dist[2]}")
        return 0

    finally:
        try:
            con.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
