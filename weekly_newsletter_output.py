# weekly_newsletter_output.py — TLCA v4 (Mac edition)
from __future__ import annotations

import os
import sqlite3
import textwrap
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

DB_PATH = os.getenv("INTEL_DB_PATH", "intel.db")
TEMPLATE_PATH = os.getenv("INTEL_TEMPLATE_PATH", "templates/newsletter_template.html")
OUT_DIR = Path(os.getenv("INTEL_OUT_DIR", "output"))
WINDOW_DAYS = int(os.getenv("INTEL_WINDOW_DAYS", "7"))
EDITION = os.getenv("INTEL_EDITION", "1")
BTN_BG = os.getenv("INTEL_BTN_BG", "#FFC72C")
BTN_TXT = os.getenv("INTEL_BTN_TXT", "#1A1A24")
BTN_LABEL = os.getenv("INTEL_BTN_LABEL", "Read the source")
MAX_PER_SOURCE = int(os.getenv("INTEL_MAX_PER_SOURCE", "2"))

SUMMARY_MAX_CHARS = 380
FALLBACK_SUMMARY = "No AI summary available. Please open the source for details."


def window_iso() -> tuple[str, str]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=WINDOW_DAYS)
    return start.isoformat(), end.isoformat()


def shorten(text: str, max_len: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rsplit(" ", 1)[0] + "…"


def fetch_articles(feed_type_filter: str) -> dict[str, list[dict]]:
    start_iso, end_iso = window_iso()
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute(
        """
        SELECT
            a.source,
            a.title,
            COALESCE(s.bullets, '') AS summary,
            COALESCE(a.clean_url, a.url),
            COALESCE(a.tags, ''),
            COALESCE(a.published_at, a.created_at)
        FROM articles a
        LEFT JOIN article_summaries s ON s.article_id = a.article_id
        WHERE a.created_at >= ? AND a.created_at < ?
          AND COALESCE(a.feed_type, 'competitor') = ?
          AND COALESCE(s.bullets, '') != ''
          AND UPPER(COALESCE(s.bullets, '')) NOT LIKE 'SKIP%'
          AND COALESCE(s.relevance_score, 2) >= 3
        ORDER BY s.relevance_score DESC, a.created_at DESC
        """,
        (start_iso, end_iso, feed_type_filter),
    )
    rows = cur.fetchall()
    con.close()

    grouped: dict[str, list[dict]] = {}
    for src, title, summary, url, tags, published in rows:
        parts = (src or "Unknown").split("_", 1)
        company = parts[0].strip()
        topic = parts[1].replace("_", "/") if len(parts) > 1 else ""
        display = f"{company} — {topic}" if topic else company

        if display not in grouped:
            grouped[display] = []

        if len(grouped[display]) < MAX_PER_SOURCE:
            grouped[display].append({
                "title": title or "(no title)",
                "summary": summary,
                "url": url or "#",
                "tags": tags,
                "published": published,
            })

    return grouped


def _tag_badges(tags_str: str) -> str:
    if not tags_str:
        return ""
    tag_list = [t.strip() for t in tags_str.split(",") if t.strip() and t.strip() != "Client_Signal"]
    if not tag_list:
        return ""
    return " ".join(
        f'<span style="background:#F0F0F8; color:#555; font-size:10px; padding:2px 7px; '
        f'border-radius:3px; margin-right:4px; display:inline-block;">{escape(t)}</span>'
        for t in tag_list
    )


def _competitor_block(display: str, items: list[dict]) -> str:
    parts = []
    for i, item in enumerate(items):
        summary = shorten(item["summary"], SUMMARY_MAX_CHARS)
        tags_html = _tag_badges(item["tags"])
        border_top = "border-top:1px solid #F0F0F8; margin-top:12px; padding-top:12px;" if i > 0 else ""

        parts.append(f"""
<div style="{border_top}">
  <div style="font-size:15px; font-weight:700; color:#1A1A24; line-height:20px;">{escape(item["title"])}</div>
  <div style="font-size:14px; margin-top:6px; line-height:21px; color:#3A3A4A;">{escape(summary)}</div>
  {f'<div style="margin-top:6px;">{tags_html}</div>' if tags_html else ''}
  <div style="margin-top:10px;">
    <a href="{escape(item["url"])}"
       style="background:{BTN_BG}; color:{BTN_TXT}; padding:6px 12px;
              text-decoration:none; font-size:12px; font-weight:700;
              border-radius:4px; display:inline-block;">
      {BTN_LABEL}
    </a>
  </div>
</div>""")

    return f"""
<table width="100%" cellpadding="0" cellspacing="0"
       style="border:1px solid #E7E7EF; margin-bottom:14px; border-collapse:collapse;">
  <tr>
    <td style="padding:14px; font-family:Arial, sans-serif;">
      <div style="font-size:12px; font-weight:700; color:#888; text-transform:uppercase;
                  letter-spacing:0.5px; margin-bottom:8px;">{escape(display)}</div>
      {"".join(parts)}
    </td>
  </tr>
</table>
"""


def _client_block(display: str, items: list[dict]) -> str:
    parts = []
    for i, item in enumerate(items):
        summary = shorten(item["summary"], SUMMARY_MAX_CHARS)
        border_top = "border-top:1px solid #F0F0F8; margin-top:10px; padding-top:10px;" if i > 0 else ""

        parts.append(f"""
<div style="{border_top}">
  <div style="font-size:14px; font-weight:700; color:#1A1A24; line-height:19px;">{escape(item["title"])}</div>
  <div style="font-size:13px; margin-top:5px; line-height:20px; color:#3A3A4A;">{escape(summary)}</div>
  <div style="margin-top:8px;">
    <a href="{escape(item["url"])}"
       style="background:#F0F0F8; color:#1A1A24; padding:5px 10px;
              text-decoration:none; font-size:12px; font-weight:700;
              border-radius:4px; display:inline-block;">
      {BTN_LABEL}
    </a>
  </div>
</div>""")

    return f"""
<table width="100%" cellpadding="0" cellspacing="0"
       style="border:1px solid #E7E7EF; margin-bottom:10px; border-collapse:collapse;">
  <tr>
    <td style="padding:12px 14px; font-family:Arial, sans-serif;">
      <div style="font-size:11px; font-weight:700; color:#888; text-transform:uppercase;
                  letter-spacing:0.5px; margin-bottom:6px;">{escape(display)}</div>
      {"".join(parts)}
    </td>
  </tr>
</table>
"""


def build_competitor_html(grouped: dict) -> str:
    if not grouped:
        return '<p style="font-family:Arial; font-size:14px; color:#6B6B78;">No competitor signals this week.</p>'
    return "\n".join(_competitor_block(display, items) for display, items in grouped.items())


def build_client_section_html(grouped: dict) -> str:
    if not grouped:
        return ""
    blocks = "\n".join(_client_block(display, items) for display, items in grouped.items())
    return f"""
<!-- CLIENT SIGNALS SECTION -->
<tr>
  <td style="padding:8px 28px 4px 28px; font-family:Arial, sans-serif;">
    <div style="font-size:16px; line-height:22px; font-weight:700; color:#1A1A24;">
      Client Signals
    </div>
    <div style="font-size:12px; line-height:18px; color:#6B6B78; margin-top:4px;">
      Market moves, CFO changes, and transformation signals from target accounts.
    </div>
  </td>
</tr>
<tr>
  <td style="padding:8px 28px 18px 28px;">
    {blocks}
  </td>
</tr>
"""


def render_html(template: str, competitor_html: str, client_section_html: str) -> str:
    now = datetime.now(timezone.utc)
    date_long = now.strftime("%d %B %Y")
    year = now.strftime("%Y")

    out = template
    out = out.replace("{{ARTICLES_HTML}}", competitor_html)
    out = out.replace("{{EY_HTML}}", "")

    if client_section_html:
        out = out.replace(
            "<!-- CONTACTS (no sign-off, just contacts) -->",
            client_section_html + "\n          <!-- CONTACTS (no sign-off, just contacts) -->"
        )

    out = out.replace("{{DATE_LONG}}", date_long)
    out = out.replace("{{EDITION}}", EDITION)
    out = out.replace("{{WINDOW_DAYS}}", str(WINDOW_DAYS))
    out = out.replace("{{YEAR}}", year)
    return out


def build_text(competitor: dict, client: dict) -> str:
    lines = ["=== COMPETITOR INTELLIGENCE ===\n"]
    for display, items in competitor.items():
        for item in items:
            lines.append(textwrap.dedent(f"""
{display.upper()}
{item["title"]}
{shorten(item["summary"], 500)}
Source: {item["url"]}
""").strip())

    if client:
        lines.append("\n=== CLIENT SIGNALS ===\n")
        for display, items in client.items():
            for item in items:
                lines.append(textwrap.dedent(f"""
{display.upper()}
{item["title"]}
{shorten(item["summary"], 500)}
Source: {item["url"]}
""").strip())

    return "\n\n".join(lines)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    competitor_grouped = fetch_articles("competitor")
    client_grouped = fetch_articles("client")

    print(f"[info] Competitor: {sum(len(v) for v in competitor_grouped.values())} articles / {len(competitor_grouped)} sources")
    print(f"[info] Client signals: {sum(len(v) for v in client_grouped.values())} articles / {len(client_grouped)} sources")

    competitor_html = build_competitor_html(competitor_grouped)
    client_section_html = build_client_section_html(client_grouped)

    try:
        template = Path(TEMPLATE_PATH).read_text(encoding="utf-8")
        full_html = render_html(template, competitor_html, client_section_html)
        (OUT_DIR / "newsletter_full.html").write_text(full_html, encoding="utf-8")
        print(" - output/newsletter_full.html")
    except FileNotFoundError:
        print(f"[WARN] Template not found at {TEMPLATE_PATH}")

    (OUT_DIR / "newsletter_block.html").write_text(competitor_html, encoding="utf-8")
    (OUT_DIR / "newsletter_block.txt").write_text(build_text(competitor_grouped, client_grouped), encoding="utf-8")

    if client_grouped:
        client_html_standalone = "\n".join(_client_block(d, i) for d, i in client_grouped.items())
        (OUT_DIR / "client_signals.html").write_text(client_html_standalone, encoding="utf-8")
        print(f" - output/client_signals.html ({len(client_grouped)} client sources)")

    print(f"[OK] Output written:")
    print(f" - output/newsletter_block.html ({len(competitor_grouped)} competitor sources)")
    print(f" - output/newsletter_block.txt")


if __name__ == "__main__":
    main()
