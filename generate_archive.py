# generate_archive.py — edition archive index for the output/ folder
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from html import escape
from pathlib import Path

OUT_ROOT = Path(os.getenv("INTEL_OUT_ROOT", "output"))
DB_PATH = os.getenv("INTEL_DB_PATH", "intel.db")
BRAND = os.getenv("INTEL_BRAND", "Competitor Intelligence")


def week_stats() -> dict[str, tuple[int, int]]:
    """Signals per edition folder key 'CW_YYYY_WW' -> (total, high)."""
    stats: dict[str, tuple[int, int]] = {}
    if not Path(DB_PATH).exists():
        return stats
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute(
            """
            SELECT a.created_at, COALESCE(s.relevance_score, 2)
            FROM articles a
            JOIN article_summaries s ON s.article_id = a.article_id
            WHERE COALESCE(s.bullets, '') != ''
              AND UPPER(COALESCE(s.bullets, '')) NOT LIKE 'SKIP%'
            """
        )
        for created_at, score in cur.fetchall():
            try:
                dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
            except ValueError:
                continue
            key = f"CW_{dt.strftime('%Y')}_{dt.strftime('%V')}"
            total, high = stats.get(key, (0, 0))
            stats[key] = (total + 1, high + (1 if int(score) == 3 else 0))
        con.close()
    except Exception:
        pass
    return stats


def collect_editions() -> list[dict]:
    editions = []
    stats = week_stats()
    if not OUT_ROOT.exists():
        return editions
    for d in sorted(OUT_ROOT.iterdir(), reverse=True):
        if not d.is_dir() or not d.name.startswith("CW_"):
            continue
        dashboard = d / "intelligence_explorer.html"
        newsletter = d / "newsletter_full.html"
        if not dashboard.exists() and not newsletter.exists():
            continue
        parts = d.name.split("_")
        label = f"CW {parts[2]} · {parts[1]}" if len(parts) == 3 else d.name
        total, high = stats.get(d.name, (0, 0))
        editions.append({
            "name": d.name,
            "label": label,
            "dashboard": dashboard.exists(),
            "newsletter": newsletter.exists(),
            "total": total,
            "high": high,
        })
    return editions


def build_html(editions: list[dict]) -> str:
    if editions:
        rows = []
        for e in editions:
            links = []
            if e["dashboard"]:
                links.append(f'<a href="{e["name"]}/intelligence_explorer.html">Dashboard</a>')
            if e["newsletter"]:
                links.append(f'<a href="{e["name"]}/newsletter_full.html">Email brief</a>')
            counts = (
                f'{e["total"]} signal{"s" if e["total"] != 1 else ""} · {e["high"]} high'
                if e["total"] else ""
            )
            rows.append(
                f'<div class="row"><span class="week">{escape(e["label"])}</span>'
                f'<span class="counts">{counts}</span>'
                f'<span class="links">{" · ".join(links)}</span></div>'
            )
        body = "".join(rows)
    else:
        body = '<div class="empty">No editions yet — run the weekly pipeline to create the first one.</div>'

    generated = datetime.now().strftime("%d %B %Y")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Edition archive</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,600&family=IBM+Plex+Sans:wght@400;600&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ background: #F4F4F1; }}
  body {{ font-family: 'IBM Plex Sans', Arial, sans-serif; color: #1A1E26; }}
  .page {{ max-width: 720px; margin: 0 auto; background: #fff; min-height: 100vh;
           border-left: 1px solid #D9DAD5; border-right: 1px solid #D9DAD5; padding: 34px 48px 60px; }}
  .eyebrow {{ font-size: 13px; font-weight: 600; }}
  h1 {{ font-family: 'Source Serif 4', Georgia, serif; font-size: 28px; font-weight: 600;
        padding: 6px 0 16px; border-bottom: 1px solid #1A1E26; }}
  .meta {{ font-size: 12.5px; color: #8A8F9C; padding: 10px 0 4px; }}
  .row {{ display: flex; align-items: baseline; gap: 18px; padding: 14px 0;
          border-bottom: 1px solid #E8E9E4; }}
  .week {{ font-family: 'Source Serif 4', Georgia, serif; font-size: 17px; font-weight: 600; min-width: 130px; }}
  .counts {{ font-size: 12.5px; color: #8A8F9C; flex: 1; }}
  .links a {{ font-size: 13px; color: #27568C; text-decoration: none; border-bottom: 1px solid #27568C; }}
  .links a:hover {{ opacity: 0.75; }}
  .empty {{ padding: 48px 0; color: #8A8F9C; font-family: 'Source Serif 4', Georgia, serif; font-size: 16px; }}
  @media (max-width: 600px) {{ .page {{ padding: 24px 20px 40px; }} .row {{ flex-wrap: wrap; gap: 8px; }} }}
</style>
</head>
<body>
<div class="page">
  <div class="eyebrow">{escape(BRAND)}</div>
  <h1>Edition archive</h1>
  <div class="meta">Every weekly edition, newest first · updated {generated}</div>
  {body}
</div>
</body>
</html>"""


def main() -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    editions = collect_editions()
    out_path = OUT_ROOT / "archive.html"
    out_path.write_text(build_html(editions), encoding="utf-8")
    print(f"[OK] Archive: {out_path} ({len(editions)} editions)")


if __name__ == "__main__":
    main()
