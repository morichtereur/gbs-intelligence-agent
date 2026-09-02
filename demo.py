# demo.py — build the dashboard and newsletter from bundled sample data.
#
# No API key, no email account, no feeds needed:
#
#   python3 demo.py
#
# Output lands in output/DEMO/. Open intelligence_explorer.html in a browser.
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from hashlib import sha1
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLE_PATH = HERE / "demo" / "sample_signals.json"
OUT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "output" / "DEMO"
DB_PATH = OUT_DIR / "demo.db"


def seed_database() -> int:
    with open(SAMPLE_PATH, encoding="utf-8") as f:
        signals = json.load(f)["signals"]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE articles (
            article_id TEXT PRIMARY KEY,
            source TEXT, title TEXT, url TEXT, clean_url TEXT,
            published_at TEXT, created_at TEXT, snippet TEXT,
            tags TEXT, feed_type TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE article_summaries (
            article_id TEXT PRIMARY KEY,
            bullets TEXT, created_at TEXT,
            relevance_score INTEGER DEFAULT 2,
            signal_type TEXT DEFAULT ''
        )
        """
    )

    now = datetime.now(timezone.utc)
    for s in signals:
        ts = f'{s["published"]}T08:00:00+00:00'
        article_id = sha1(f"{s['source']}|{s['url']}".encode()).hexdigest()
        cur.execute(
            "INSERT INTO articles VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                article_id, s["source"], s["title"], s["url"], s["url"],
                ts, ts, s["summary"], ",".join(s["tags"]), s["feed_type"],
            ),
        )
        cur.execute(
            "INSERT INTO article_summaries VALUES (?,?,?,?,?)",
            (article_id, s["summary"], ts, s["score"], s.get("signal_type", "")),
        )
    con.commit()
    con.close()
    return len(signals)


def run_stage(script: str, env: dict) -> None:
    result = subprocess.run([sys.executable, str(HERE / script)], env=env, cwd=HERE)
    if result.returncode != 0:
        raise SystemExit(f"[ERROR] {script} failed with exit code {result.returncode}")


def main() -> None:
    count = seed_database()
    print(f"[demo] Seeded {count} sample signals into {DB_PATH}")

    period_start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    window_days = max(63, (datetime.now(timezone.utc) - period_start).days + 2)

    env = {
        **os.environ,
        "INTEL_DB_PATH": str(DB_PATH),
        "INTEL_OUT_DIR": str(OUT_DIR),
        "INTEL_SOURCES_PATH": str(HERE / "sources.example.json"),
        "INTEL_TEMPLATE_PATH": str(HERE / "templates" / "newsletter_template.html"),
        "INTEL_WINDOW_DAYS": str(window_days),
        "INTEL_DASHBOARD_WEEKS": str((window_days // 7) + 1),
        "INTEL_MIN_SCORE": "3",
        "INTEL_EDITION": "17",
        "INTEL_DEMO_LABEL": "Demo data",
        "INTEL_PERIOD_LABEL": "July \u2013 August 2026",
        "INTEL_OG_IMAGE": "https://morichtereur.github.io/gbs-intelligence-agent/og-card.png",
        "INTEL_OG_URL": "https://morichtereur.github.io/gbs-intelligence-agent/",
        "INTEL_OWNER_NAME": "Moritz Richter",
        "INTEL_OWNER_URL": "https://morichtereur.github.io/",
        "INTEL_ORG_NAME": "GBS Intelligence Agent — Demo",
        "INTEL_FEEDBACK_EMAIL": "feedback@example.com",
    }

    run_stage("generate_dashboard.py", env)
    run_stage("weekly_newsletter_output.py", env)

    print()
    print("[demo] Done. Open these in a browser:")
    print(f"       {OUT_DIR / 'intelligence_explorer.html'}")
    print(f"       {OUT_DIR / 'newsletter_full.html'}")


if __name__ == "__main__":
    main()
