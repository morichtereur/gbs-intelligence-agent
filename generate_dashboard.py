# generate_dashboard.py — Intelligence Explorer v3 (consulting-exhibit edition)
from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

DB_PATH = os.getenv("INTEL_DB_PATH", "intel.db")
SOURCES_PATH = os.getenv("INTEL_SOURCES_PATH", "sources.json")
OUT_DIR = Path(os.getenv("INTEL_OUT_DIR", "output"))
WINDOW_WEEKS = int(os.getenv("INTEL_DASHBOARD_WEEKS", "4"))
EDITION = os.getenv("INTEL_EDITION", "")

# Branding — all optional, so the public repo ships with neutral defaults.
BRAND = os.getenv("INTEL_BRAND", "Competitor & Client Intelligence")
OWNER_NAME = os.getenv("INTEL_OWNER_NAME", "").strip()
OWNER_TITLE = os.getenv("INTEL_OWNER_TITLE", "").strip()
OWNER_EMAIL = os.getenv("INTEL_OWNER_EMAIL", "").strip()
DEMO_LABEL = os.getenv("INTEL_DEMO_LABEL", "").strip()

TAG_LABELS = {
    "GBS": "GBS",
    "GCC": "GCC",
    "Agentic_AI": "Agentic AI",
    "Operating_Model": "Operating model",
    "Analyst_Research": "Analyst research",
}
CLUSTER_ORDER = ["MBB", "Big4", "Accenture", "Other"]

# Sequential single-hue ramp (light -> dark) for the firm x theme matrix.
HEAT_RAMP = ["#F1F5FA", "#D9E4F0", "#B3C9E1", "#82A6CB", "#4F7BAA", "#27568C"]


def tag_label(tag: str) -> str:
    return TAG_LABELS.get(tag, tag.replace("_", " "))


def fetch_all_signals() -> list[dict]:
    start = (datetime.now(timezone.utc) - timedelta(weeks=WINDOW_WEEKS)).isoformat()
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        SELECT
            a.source,
            a.title,
            COALESCE(a.clean_url, a.url) as url,
            COALESCE(a.tags, '') as tags,
            COALESCE(a.feed_type, 'competitor') as feed_type,
            a.created_at,
            COALESCE(s.bullets, '') as summary,
            COALESCE(s.relevance_score, 2) as relevance_score
        FROM articles a
        LEFT JOIN article_summaries s ON s.article_id = a.article_id
        WHERE a.created_at >= ?
          AND COALESCE(s.bullets, '') != ''
          AND UPPER(COALESCE(s.bullets, '')) NOT LIKE 'SKIP%'
        ORDER BY a.created_at DESC
        """,
        (start,),
    )
    rows = cur.fetchall()
    con.close()

    # Load firm clusters from sources.json
    try:
        with open(SOURCES_PATH, encoding="utf-8") as cf:
            scfg = json.load(cf)
        firm_clusters = scfg.get("firm_clusters", {})
        company_to_cluster = {}
        for cluster, firms in firm_clusters.items():
            for firm in firms:
                company_to_cluster[firm.lower()] = cluster
    except Exception:
        company_to_cluster = {}

    signals = []
    for src, title, url, tags, feed_type, created_at, summary, score in rows:
        parts = (src or "Unknown").split("_", 1)
        company = parts[0].strip()
        topic = parts[1].replace("_", "/") if len(parts) > 1 else ""

        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            cw = f"CW {dt.strftime('%V')}"
            week_label = f"CW {dt.strftime('%V')}"
            week_sort = dt.strftime("%G-%V")
        except Exception:
            cw = "—"
            week_label = "—"
            week_sort = ""

        tag_list = [t.strip() for t in tags.split(",") if t.strip() and t.strip() != "Client_Signal"]
        cluster = company_to_cluster.get(company.lower(), "Other")

        signals.append({
            "source": src,
            "company": company,
            "topic": topic,
            "title": title or "(no title)",
            "url": url or "#",
            "tags": tag_list,
            "feed_type": feed_type,
            "created_at": created_at,
            "cw": cw,
            "week_label": week_label,
            "week_sort": week_sort,
            "summary": summary,
            "score": int(score),
            "cluster": cluster,
        })

    return signals


def embed_photo() -> str:
    """Embed photo.jpg as base64 img tag, or return empty string."""
    import base64
    photo_path = Path(os.getenv("INTEL_PHOTO_PATH", "photo.jpg"))
    if photo_path.exists():
        with open(photo_path, "rb") as pf:
            img_b64 = base64.b64encode(pf.read()).decode("utf-8")
        ext = photo_path.suffix.lower().replace(".", "")
        mime = "jpeg" if ext in ("jpg", "jpeg") else ext
        return (
            f'<img src="data:image/{mime};base64,{img_b64}" '
            f'style="width:42px; height:42px; border-radius:50%; object-fit:cover; border:1px solid #D9DAD5;" alt="">'
        )
    return ""


# ---------------------------------------------------------------- aggregates

def week_series(signals: list[dict]) -> list[dict]:
    """Every ISO week touched by the window (oldest first) with competitor/client counts."""
    now = datetime.now(timezone.utc)
    weeks: list[dict] = []
    seen: set[str] = set()
    for days_back in range(WINDOW_WEEKS * 7, -1, -1):
        d = now - timedelta(days=days_back)
        key = d.strftime("%G-%V")
        if key in seen:
            continue
        seen.add(key)
        weeks.append({"key": key, "label": f"CW {d.strftime('%V')}", "competitor": 0, "client": 0})
    by_key = {w["key"]: w for w in weeks}
    for s in signals:
        w = by_key.get(s["week_sort"])
        if w is None:
            continue
        if s["feed_type"] == "client":
            w["client"] += 1
        else:
            w["competitor"] += 1
    return weeks


def firm_theme_matrix(signals: list[dict]) -> tuple[list[str], list[dict]]:
    """Competitor signals only: rows = firms (grouped by cluster), cols = themes."""
    comp = [s for s in signals if s["feed_type"] == "competitor"]
    col_counter: Counter[str] = Counter(t for s in comp for t in s["tags"])
    columns = [t for t in TAG_LABELS if t in col_counter]

    cells: dict[str, Counter] = {}
    clusters: dict[str, str] = {}
    for s in comp:
        firm = s["company"]
        clusters[firm] = s["cluster"]
        c = cells.setdefault(firm, Counter())
        for t in s["tags"]:
            if t in columns:
                c[t] += 1

    rows = []
    for firm, counter in cells.items():
        rows.append({
            "firm": firm,
            "cluster": clusters.get(firm, "Other"),
            "counts": [counter.get(t, 0) for t in columns],
            "total": sum(counter.get(t, 0) for t in columns),
        })
    rows.sort(key=lambda r: (
        CLUSTER_ORDER.index(r["cluster"]) if r["cluster"] in CLUSTER_ORDER else len(CLUSTER_ORDER),
        -r["total"],
        r["firm"],
    ))
    return columns, rows


def compute_headline(signals: list[dict]) -> tuple[str, str]:
    """Answer-first action title + supporting deck line, derived purely from the data."""
    if not signals:
        return (
            "No new signals in the reporting window",
            "The pipeline ran, but no articles cleared the relevance filters. "
            "Check feed configuration or widen the window.",
        )

    comp = [s for s in signals if s["feed_type"] == "competitor"]
    clients = [s for s in signals if s["feed_type"] == "client"]
    high = sum(1 for s in signals if s["score"] == 3)
    n_orgs = len({s["company"] for s in signals})

    deck = (
        f"{len(signals)} signals from {n_orgs} organisations in the last {WINDOW_WEEKS * 7} days — "
        f"{high} rated high relevance, {len(clients)} from client accounts."
    )

    if comp:
        theme_counts = Counter(t for s in comp for t in s["tags"])
        firm_counts = Counter(s["company"] for s in comp)
        if theme_counts:
            top_theme, _ = theme_counts.most_common(1)[0]
            top_firm, n_firm = firm_counts.most_common(1)[0]
            headline = (
                f"{tag_label(top_theme)} leads competitor publishing; "
                f"{top_firm} most active with {n_firm} signal{'s' if n_firm != 1 else ''}"
            )
            return headline, deck
        top_firm, n_firm = firm_counts.most_common(1)[0]
        return f"{top_firm} drives competitor activity with {n_firm} signal{'s' if n_firm != 1 else ''}", deck

    return f"{len(clients)} client signal{'s' if len(clients) != 1 else ''} flagged this period", deck


# ---------------------------------------------------------------- rendering

def render_kpis(signals: list[dict]) -> str:
    comp = [s for s in signals if s["feed_type"] == "competitor"]
    high = sum(1 for s in signals if s["score"] == 3)
    n_orgs = len({s["company"] for s in signals})
    firm_counts = Counter(s["company"] for s in comp)
    top_firm = firm_counts.most_common(1)[0][0] if firm_counts else "—"

    tiles = [
        (str(len(signals)), "signals captured"),
        (str(high), "high relevance (★)"),
        (str(n_orgs), "organisations tracked"),
        (top_firm, "most active firm"),
    ]
    out = []
    for value, label in tiles:
        out.append(
            f'<div class="kpi"><div class="kpi-value">{escape(value)}</div>'
            f'<div class="kpi-label">{escape(label)}</div></div>'
        )
    return "\n".join(out)


def render_week_bars(weeks: list[dict]) -> str:
    max_count = max([w["competitor"] for w in weeks] + [w["client"] for w in weeks] + [1])
    groups = []
    for w in weeks:
        bars = []
        for series, cls in (("competitor", "bar-comp"), ("client", "bar-client")):
            count = w[series]
            h = round(count / max_count * 120) if count else 2
            label = f'<span class="bar-value">{count}</span>' if count else ""
            bars.append(
                f'<div class="bar {cls}" style="height:{h}px" '
                f'data-tip="{escape(w["label"])}: {count} {series} signal{"s" if count != 1 else ""}">{label}</div>'
            )
        groups.append(
            f'<div class="bar-group"><div class="bars">{"".join(bars)}</div>'
            f'<div class="bar-week">{escape(w["label"])}</div></div>'
        )
    return "\n".join(groups)


def render_matrix(columns: list[str], rows: list[dict]) -> str:
    if not rows:
        return '<div class="empty-note">No competitor signals in the window.</div>'

    max_cell = max((max(r["counts"]) for r in rows if r["counts"]), default=1) or 1

    head = "".join(f'<th class="mx-col">{escape(tag_label(c))}</th>' for c in columns)
    body_rows = []
    prev_cluster = None
    for r in rows:
        cluster_cell = ""
        if r["cluster"] != prev_cluster:
            span = sum(1 for x in rows if x["cluster"] == r["cluster"])
            cluster_cell = f'<td class="mx-cluster" rowspan="{span}">{escape(r["cluster"])}</td>'
            prev_cluster = r["cluster"]
        cells = []
        for c in r["counts"]:
            if c == 0:
                cells.append('<td class="mx-cell mx-zero">·</td>')
            else:
                step = min(len(HEAT_RAMP) - 1, max(1, round(c / max_cell * (len(HEAT_RAMP) - 1))))
                color = HEAT_RAMP[step]
                ink = "#FFFFFF" if step >= 3 else "#1A1E26"
                cells.append(f'<td class="mx-cell" style="background:{color}; color:{ink};">{c}</td>')
        body_rows.append(
            f'<tr>{cluster_cell}<td class="mx-firm">{escape(r["firm"])}</td>'
            f'{"".join(cells)}<td class="mx-total">{r["total"]}</td></tr>'
        )
    return (
        '<table class="matrix"><thead><tr><th></th><th></th>'
        + head + '<th class="mx-col">Total</th></tr></thead><tbody>'
        + "".join(body_rows) + "</tbody></table>"
    )


def render_footer() -> str:
    if OWNER_NAME:
        photo = embed_photo()
        title_html = f'<div class="foot-role">{escape(OWNER_TITLE)}</div>' if OWNER_TITLE else ""
        email_html = (
            f'<a class="foot-mail" href="mailto:{escape(OWNER_EMAIL)}">{escape(OWNER_EMAIL)}</a>'
            if OWNER_EMAIL else ""
        )
        return (
            f'<div class="foot-owner">{photo}<div>'
            f'<div class="foot-name">{escape(OWNER_NAME)}</div>{title_html}{email_html}</div></div>'
        )
    return (
        '<div class="foot-name">Generated by the '
        '<a class="foot-mail" href="https://github.com/morichtereur/gbs-intelligence-agent">GBS Intelligence Agent</a></div>'
    )


def build_html(signals: list[dict]) -> str:
    # Prevent article content from closing the inline script tag.
    signals_json = json.dumps(signals, ensure_ascii=False).replace("<", "\\u003c")

    headline, deck = compute_headline(signals)
    weeks = week_series(signals)
    columns, mx_rows = firm_theme_matrix(signals)

    all_tags = sorted({t for s in signals for t in s["tags"]})
    all_weeks = sorted({s["week_label"] for s in signals if s["week_label"] != "—"}, reverse=True)
    now = datetime.now(timezone.utc).strftime("%d %B %Y")
    edition_html = f"Edition {escape(EDITION)} · " if EDITION else ""
    demo_chip = f'<span class="demo-chip">{escape(DEMO_LABEL)}</span>' if DEMO_LABEL else ""

    tag_pills = "\n".join(
        f'<button class="pill" data-filter="tag" data-value="{escape(t)}">{escape(tag_label(t))}</button>'
        for t in all_tags
    )
    week_pills = "\n".join(
        f'<button class="pill" data-filter="week" data-value="{escape(w)}">{escape(w)}</button>'
        for w in all_weeks
    )

    html = HTML_TEMPLATE
    replacements = {
        "__BRAND__": escape(BRAND),
        "__EDITION__": edition_html,
        "__DEMO_CHIP__": demo_chip,
        "__DATE__": now,
        "__WINDOW_DAYS__": str(WINDOW_WEEKS * 7),
        "__HEADLINE__": escape(headline),
        "__DECK__": escape(deck),
        "__KPIS__": render_kpis(signals),
        "__WEEK_BARS__": render_week_bars(weeks),
        "__MATRIX__": render_matrix(columns, mx_rows),
        "__TAG_PILLS__": tag_pills,
        "__WEEK_PILLS__": week_pills,
        "__FOOTER_IDENTITY__": render_footer(),
        "__SIGNALS_JSON__": signals_json,
    }
    for token, value in replacements.items():
        html = html.replace(token, value)
    return html


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Intelligence Explorer</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --stock: #F4F4F1;
      --paper: #FFFFFF;
      --ink: #1A1E26;
      --ink-2: #4C5361;
      --ink-3: #8A8F9C;
      --rule: #D9DAD5;
      --rule-soft: #E8E9E4;
      --accent: #27568C;
      --accent-soft: #EAF0F7;
      --client: #0E9F6E;
      --client-soft: #E7F5EF;
      --serif: 'Source Serif 4', Georgia, serif;
      --sans: 'IBM Plex Sans', 'Helvetica Neue', Arial, sans-serif;
      --mono: 'IBM Plex Mono', 'SF Mono', Menlo, monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    html { background: var(--stock); }
    body {
      font-family: var(--sans);
      color: var(--ink);
      line-height: 1.5;
      background: var(--stock);
      -webkit-font-smoothing: antialiased;
    }

    .page {
      max-width: 1060px;
      margin: 0 auto;
      background: var(--paper);
      min-height: 100vh;
      border-left: 1px solid var(--rule);
      border-right: 1px solid var(--rule);
    }

    /* ── Masthead ── */
    .masthead {
      padding: 26px 48px 0;
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 16px;
    }
    .eyebrow {
      font-family: var(--mono);
      font-size: 11px;
      letter-spacing: 2.5px;
      text-transform: uppercase;
      color: var(--accent);
      font-weight: 500;
    }
    .masthead-meta {
      font-family: var(--mono);
      font-size: 11px;
      color: var(--ink-3);
      text-align: right;
      white-space: nowrap;
    }
    .demo-chip {
      display: inline-block;
      font-family: var(--mono);
      font-size: 10px;
      letter-spacing: 1px;
      text-transform: uppercase;
      color: var(--paper);
      background: var(--accent);
      padding: 2px 8px;
      border-radius: 2px;
      margin-left: 10px;
      vertical-align: 2px;
    }

    /* ── Headline (the answer) ── */
    .lede {
      padding: 14px 48px 26px;
      border-bottom: 1px solid var(--ink);
    }
    .lede h1 {
      font-family: var(--serif);
      font-size: clamp(26px, 4vw, 38px);
      font-weight: 600;
      line-height: 1.18;
      letter-spacing: -0.4px;
      max-width: 21em;
    }
    .lede .deck {
      margin-top: 10px;
      font-size: 15px;
      color: var(--ink-2);
      max-width: 46em;
    }

    /* ── KPI strip ── */
    .kpis {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      border-bottom: 1px solid var(--rule);
    }
    .kpi {
      padding: 18px 24px 16px;
      border-right: 1px solid var(--rule-soft);
    }
    .kpi:first-child { padding-left: 48px; }
    .kpi:last-child { border-right: none; }
    .kpi-value {
      font-family: var(--serif);
      font-size: 30px;
      font-weight: 600;
      line-height: 1.1;
      color: var(--ink);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .kpi-label {
      font-family: var(--mono);
      font-size: 10.5px;
      letter-spacing: 0.8px;
      text-transform: uppercase;
      color: var(--ink-3);
      margin-top: 5px;
    }

    /* ── Exhibits ── */
    .exhibits {
      display: grid;
      grid-template-columns: 5fr 7fr;
      gap: 0;
      border-bottom: 1px solid var(--rule);
    }
    .exhibit {
      padding: 24px 32px 26px 48px;
      min-width: 0;
    }
    .exhibit + .exhibit {
      border-left: 1px solid var(--rule-soft);
      padding-left: 32px;
      padding-right: 48px;
    }
    .exhibit-eyebrow {
      font-family: var(--mono);
      font-size: 10.5px;
      letter-spacing: 1.5px;
      text-transform: uppercase;
      color: var(--ink-3);
    }
    .exhibit-title {
      font-family: var(--serif);
      font-size: 17px;
      font-weight: 600;
      margin-top: 4px;
      margin-bottom: 18px;
    }

    /* Exhibit 1: bars */
    .chart {
      display: flex;
      align-items: flex-end;
      gap: 22px;
      height: 160px;
      padding-bottom: 2px;
      border-bottom: 1px solid var(--ink);
    }
    .bar-group { display: flex; flex-direction: column; justify-content: flex-end; height: 100%; }
    .bars { display: flex; align-items: flex-end; gap: 3px; flex: 1; }
    .bar {
      width: 26px;
      border-radius: 3px 3px 0 0;
      position: relative;
      display: flex;
      justify-content: center;
    }
    .bar-comp { background: var(--accent); }
    .bar-client { background: var(--client); }
    .bar-value {
      position: absolute;
      top: -18px;
      font-family: var(--mono);
      font-size: 10.5px;
      color: var(--ink-2);
    }
    .bar-week {
      font-family: var(--mono);
      font-size: 10.5px;
      color: var(--ink-3);
      text-align: center;
      margin-top: 7px;
    }
    .legend { display: flex; gap: 18px; margin-top: 12px; }
    .legend-item {
      display: flex; align-items: center; gap: 7px;
      font-size: 12px; color: var(--ink-2);
    }
    .legend-swatch { width: 10px; height: 10px; border-radius: 2px; }

    /* Exhibit 2: matrix */
    .matrix-scroll { overflow-x: auto; }
    .matrix { border-collapse: separate; border-spacing: 2px; width: 100%; }
    .matrix th {
      font-family: var(--mono);
      font-size: 10px;
      letter-spacing: 0.5px;
      text-transform: uppercase;
      color: var(--ink-3);
      font-weight: 500;
      text-align: center;
      padding: 0 6px 6px;
      white-space: nowrap;
    }
    .mx-cluster {
      font-family: var(--mono);
      font-size: 10px;
      letter-spacing: 1px;
      text-transform: uppercase;
      color: var(--ink-3);
      vertical-align: top;
      padding: 5px 10px 0 0;
      white-space: nowrap;
    }
    .mx-firm {
      font-size: 12.5px;
      font-weight: 500;
      padding: 3px 12px 3px 0;
      white-space: nowrap;
    }
    .mx-cell {
      font-family: var(--mono);
      font-size: 11.5px;
      text-align: center;
      min-width: 44px;
      padding: 5px 0;
      border-radius: 2px;
    }
    .mx-zero { color: var(--rule); background: transparent; }
    .mx-total {
      font-family: var(--mono);
      font-size: 11.5px;
      font-weight: 500;
      text-align: center;
      color: var(--ink-2);
      padding: 5px 0 5px 8px;
    }
    .exhibit-note {
      font-size: 11px;
      color: var(--ink-3);
      margin-top: 12px;
    }

    /* ── Register ── */
    .register-head {
      padding: 26px 48px 0;
    }
    .register-head h2 {
      font-family: var(--serif);
      font-size: 21px;
      font-weight: 600;
    }
    .register-sub { font-size: 13px; color: var(--ink-2); margin-top: 3px; }

    .filters {
      padding: 16px 48px 14px;
      display: flex;
      gap: 24px;
      flex-wrap: wrap;
      align-items: flex-end;
      border-bottom: 1px solid var(--rule);
      position: sticky;
      top: 0;
      background: rgba(255,255,255,0.96);
      backdrop-filter: blur(6px);
      z-index: 40;
    }
    .filter-group { display: flex; flex-direction: column; gap: 6px; }
    .filter-label {
      font-family: var(--mono);
      font-size: 9.5px;
      letter-spacing: 1.2px;
      text-transform: uppercase;
      color: var(--ink-3);
    }
    .filter-pills { display: flex; gap: 4px; flex-wrap: wrap; }
    .pill {
      font-family: var(--sans);
      font-size: 12px;
      padding: 4px 11px;
      border: 1px solid var(--rule);
      border-radius: 2px;
      background: var(--paper);
      color: var(--ink-2);
      cursor: pointer;
      transition: all 0.1s ease;
    }
    .pill:hover { border-color: var(--accent); color: var(--accent); }
    .pill.active {
      background: var(--ink);
      border-color: var(--ink);
      color: var(--paper);
    }
    .search-wrap { flex: 1; min-width: 200px; }
    .search-input {
      width: 100%;
      font-family: var(--sans);
      font-size: 13px;
      padding: 6px 12px;
      border: 1px solid var(--rule);
      border-radius: 2px;
      color: var(--ink);
      background: var(--paper);
      outline: none;
    }
    .search-input:focus { border-color: var(--accent); }
    .kbd-hint {
      font-family: var(--mono);
      font-size: 10px;
      color: var(--ink-3);
      margin-left: auto;
      align-self: center;
      white-space: nowrap;
    }
    .kbd {
      border: 1px solid var(--rule);
      border-radius: 2px;
      padding: 1px 5px;
      background: var(--stock);
    }

    .register { padding: 6px 48px 40px; }

    .section-label {
      font-family: var(--mono);
      font-size: 10.5px;
      letter-spacing: 1.5px;
      text-transform: uppercase;
      padding: 20px 0 8px;
      border-bottom: 1px solid var(--ink);
      margin-bottom: 2px;
      display: flex;
      justify-content: space-between;
      align-items: baseline;
    }
    .section-label .count { color: var(--ink-3); letter-spacing: 0.5px; }
    .sec-comp { color: var(--accent); }
    .sec-client { color: var(--client); }

    .row {
      border-bottom: 1px solid var(--rule-soft);
      cursor: pointer;
    }
    .row-line {
      display: grid;
      grid-template-columns: 64px 168px 1fr 56px;
      gap: 14px;
      align-items: baseline;
      padding: 11px 0;
    }
    .row:hover .row-title { color: var(--accent); }

    .score {
      font-family: var(--mono);
      font-size: 10px;
      font-weight: 500;
      letter-spacing: 0.5px;
      text-align: center;
      padding: 2px 0;
      border-radius: 2px;
      white-space: nowrap;
    }
    .score-3 { background: var(--accent); color: var(--paper); }
    .score-2 { background: var(--accent-soft); color: var(--accent); }
    .score-1 { background: var(--stock); color: var(--ink-3); }

    .row-firm {
      font-family: var(--mono);
      font-size: 11px;
      letter-spacing: 0.3px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .row-firm.competitor { color: var(--accent); }
    .row-firm.client { color: var(--client); }
    .row-firm .topic { color: var(--ink-3); }

    .row-title {
      font-size: 13.5px;
      font-weight: 500;
      line-height: 1.4;
      transition: color 0.1s;
    }
    .row-cw {
      font-family: var(--mono);
      font-size: 10.5px;
      color: var(--ink-3);
      text-align: right;
    }

    .row-detail {
      display: none;
      padding: 2px 0 16px 78px;
      max-width: 720px;
    }
    .row.open .row-detail { display: block; }
    .row.open { background: linear-gradient(to right, var(--accent) 2px, transparent 2px); }
    .detail-summary {
      font-family: var(--serif);
      font-size: 14.5px;
      line-height: 1.65;
      color: var(--ink-2);
    }
    .detail-meta { display: flex; gap: 8px; align-items: center; margin-top: 12px; flex-wrap: wrap; }
    .tagchip {
      font-family: var(--mono);
      font-size: 10px;
      letter-spacing: 0.5px;
      padding: 2px 8px;
      border: 1px solid var(--rule);
      border-radius: 2px;
      color: var(--ink-2);
    }
    .source-link {
      font-family: var(--mono);
      font-size: 11px;
      color: var(--accent);
      text-decoration: none;
      border-bottom: 1px solid var(--accent);
      padding-bottom: 1px;
    }
    .source-link:hover { opacity: 0.75; }

    .empty-note {
      padding: 40px 0;
      text-align: center;
      color: var(--ink-3);
      font-family: var(--serif);
      font-size: 16px;
    }

    /* ── Footer ── */
    .foot {
      border-top: 1px solid var(--ink);
      padding: 20px 48px 28px;
      display: flex;
      justify-content: space-between;
      gap: 24px;
      align-items: flex-start;
    }
    .foot-owner { display: flex; gap: 12px; align-items: center; }
    .foot-name { font-size: 13px; font-weight: 600; }
    .foot-role { font-size: 11.5px; color: var(--ink-2); }
    .foot-mail {
      font-family: var(--mono);
      font-size: 11px;
      color: var(--accent);
      text-decoration: none;
    }
    .foot-method {
      font-size: 10.5px;
      color: var(--ink-3);
      text-align: right;
      max-width: 46em;
      line-height: 1.6;
    }

    /* ── Tooltip ── */
    .tip {
      position: fixed;
      pointer-events: none;
      background: var(--ink);
      color: var(--paper);
      font-family: var(--mono);
      font-size: 11px;
      padding: 5px 9px;
      border-radius: 2px;
      z-index: 100;
      display: none;
      white-space: nowrap;
    }

    /* ── Responsive ── */
    @media (max-width: 860px) {
      .masthead, .lede, .register-head, .filters, .register, .foot { padding-left: 22px; padding-right: 22px; }
      .exhibits { grid-template-columns: 1fr; }
      .exhibit, .exhibit + .exhibit { padding: 22px; border-left: none; }
      .exhibit + .exhibit { border-top: 1px solid var(--rule-soft); }
      .kpis { grid-template-columns: repeat(2, 1fr); }
      .kpi, .kpi:first-child { padding: 14px 22px; }
      .row-line { grid-template-columns: 56px 1fr 48px; }
      .row-firm { grid-column: 2; }
      .row-title { grid-column: 1 / -1; }
      .row-detail { padding-left: 0; }
      .foot { flex-direction: column; }
      .foot-method { text-align: left; }
    }

    @media print {
      html, body { background: #fff; }
      .page { border: none; max-width: none; }
      .filters, .kbd-hint { display: none; }
      .row-detail { display: block; }
      .row { break-inside: avoid; }
    }
  </style>
</head>
<body>
<div class="page">

  <div class="masthead">
    <div class="eyebrow">__BRAND__ __DEMO_CHIP__</div>
    <div class="masthead-meta">__EDITION__Generated __DATE__ · Last __WINDOW_DAYS__ days</div>
  </div>

  <div class="lede">
    <h1>__HEADLINE__</h1>
    <div class="deck">__DECK__</div>
  </div>

  <div class="kpis">
    __KPIS__
  </div>

  <div class="exhibits">
    <div class="exhibit">
      <div class="exhibit-eyebrow">Exhibit 1</div>
      <div class="exhibit-title">Signal volume by calendar week</div>
      <div class="chart" id="chart">
        __WEEK_BARS__
      </div>
      <div class="legend">
        <div class="legend-item"><span class="legend-swatch" style="background:var(--accent)"></span>Competitor</div>
        <div class="legend-item"><span class="legend-swatch" style="background:var(--client)"></span>Client</div>
      </div>
    </div>
    <div class="exhibit">
      <div class="exhibit-eyebrow">Exhibit 2</div>
      <div class="exhibit-title">Where competitors publish — firm &times; theme</div>
      <div class="matrix-scroll">
        __MATRIX__
      </div>
      <div class="exhibit-note">Competitor signals only; a signal may carry several themes. Darker cells = more signals.</div>
    </div>
  </div>

  <div class="register-head">
    <h2>Signal register</h2>
    <div class="register-sub">Every captured signal in the window, ranked by relevance. Click a row for the full summary.</div>
  </div>

  <div class="filters">
    <div class="filter-group">
      <div class="filter-label">Type</div>
      <div class="filter-pills">
        <button class="pill active" data-filter="type" data-value="all">All</button>
        <button class="pill" data-filter="type" data-value="competitor">Competitor</button>
        <button class="pill" data-filter="type" data-value="client">Client</button>
      </div>
    </div>
    <div class="filter-group">
      <div class="filter-label">Theme</div>
      <div class="filter-pills">
        <button class="pill active" data-filter="tag" data-value="all">All</button>
        __TAG_PILLS__
      </div>
    </div>
    <div class="filter-group">
      <div class="filter-label">Relevance</div>
      <div class="filter-pills">
        <button class="pill active" data-filter="score" data-value="all">All</button>
        <button class="pill" data-filter="score" data-value="3">&#9733; High</button>
        <button class="pill" data-filter="score" data-value="2">Med</button>
        <button class="pill" data-filter="score" data-value="1">Low</button>
      </div>
    </div>
    <div class="filter-group">
      <div class="filter-label">Week</div>
      <div class="filter-pills">
        <button class="pill active" data-filter="week" data-value="all">All</button>
        __WEEK_PILLS__
      </div>
    </div>
    <div class="filter-group search-wrap">
      <div class="filter-label">Search</div>
      <input class="search-input" id="search" type="text" placeholder="Titles, summaries, firms&hellip;">
    </div>
    <div class="kbd-hint"><span class="kbd">/</span> search &nbsp;<span class="kbd">Esc</span> reset</div>
  </div>

  <div class="register" id="register"></div>

  <div class="foot">
    __FOOTER_IDENTITY__
    <div class="foot-method">
      Method: public sources monitored via Google Alerts RSS &middot; relevance scored 1&ndash;3 and summarised by Claude &middot;
      summaries are AI-generated and should be verified against the source before use.
    </div>
  </div>

</div>

<div class="tip" id="tip"></div>

<script>
const SIGNALS = __SIGNALS_JSON__;

const SCORE_LABEL = { 3: '★ HIGH', 2: 'MED', 1: 'LOW' };

let filters = { type: 'all', tag: 'all', score: 'all', week: 'all', search: '' };

function escHtml(s) {
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function matches(s) {
  if (filters.type !== 'all' && s.feed_type !== filters.type) return false;
  if (filters.tag !== 'all' && !s.tags.includes(filters.tag)) return false;
  if (filters.score !== 'all' && String(s.score) !== filters.score) return false;
  if (filters.week !== 'all' && s.week_label !== filters.week) return false;
  if (filters.search) {
    const q = filters.search.toLowerCase();
    if (!(s.title + ' ' + s.summary + ' ' + s.company + ' ' + s.topic).toLowerCase().includes(q)) return false;
  }
  return true;
}

function rowHtml(s) {
  const firm = escHtml(s.company) + (s.topic ? ' <span class="topic">&middot; ' + escHtml(s.topic) + '</span>' : '');
  const tags = s.tags.map(t => '<span class="tagchip">' + escHtml(t.replace(/_/g, ' ')) + '</span>').join('');
  return '<div class="row">' +
    '<div class="row-line">' +
      '<span class="score score-' + s.score + '">' + (SCORE_LABEL[s.score] || s.score) + '</span>' +
      '<span class="row-firm ' + s.feed_type + '">' + firm + '</span>' +
      '<span class="row-title">' + escHtml(s.title) + '</span>' +
      '<span class="row-cw">' + escHtml(s.cw) + '</span>' +
    '</div>' +
    '<div class="row-detail">' +
      '<div class="detail-summary">' + escHtml(s.summary || 'No summary available.') + '</div>' +
      '<div class="detail-meta">' + tags +
        '<a class="source-link" href="' + escHtml(s.url) + '" target="_blank" rel="noopener">Read the source &rarr;</a>' +
      '</div>' +
    '</div>' +
  '</div>';
}

function sortSignals(list) {
  return list.slice().sort((a, b) => (b.score - a.score) || (a.created_at < b.created_at ? 1 : -1));
}

function render() {
  const el = document.getElementById('register');
  const visible = SIGNALS.filter(matches);

  if (!visible.length) {
    el.innerHTML = '<div class="empty-note">No signals match the current filters.</div>';
    return;
  }

  const comp = sortSignals(visible.filter(s => s.feed_type === 'competitor'));
  const cli  = sortSignals(visible.filter(s => s.feed_type === 'client'));

  let html = '';
  if (comp.length) {
    html += '<div class="section-label sec-comp"><span>Competitor intelligence</span><span class="count">' + comp.length + '</span></div>';
    html += comp.map(rowHtml).join('');
  }
  if (cli.length) {
    html += '<div class="section-label sec-client"><span>Client signals</span><span class="count">' + cli.length + '</span></div>';
    html += cli.map(rowHtml).join('');
  }
  el.innerHTML = html;
}

document.getElementById('register').addEventListener('click', e => {
  if (e.target.closest('a')) return;
  const row = e.target.closest('.row');
  if (row) row.classList.toggle('open');
});

document.querySelectorAll('.pill[data-filter]').forEach(pill => {
  pill.addEventListener('click', () => {
    const ft = pill.dataset.filter;
    document.querySelectorAll('.pill[data-filter="' + ft + '"]').forEach(p => p.classList.remove('active'));
    pill.classList.add('active');
    filters[ft] = pill.dataset.value;
    render();
  });
});

document.getElementById('search').addEventListener('input', e => {
  filters.search = e.target.value.trim();
  render();
});

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    filters = { type: 'all', tag: 'all', score: 'all', week: 'all', search: '' };
    document.getElementById('search').value = '';
    document.querySelectorAll('.pill').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.pill[data-value="all"]').forEach(p => p.classList.add('active'));
    render();
  }
  if (e.key === '/' && document.activeElement !== document.getElementById('search')) {
    e.preventDefault();
    document.getElementById('search').focus();
  }
});

// Bar tooltips
const tip = document.getElementById('tip');
document.querySelectorAll('.bar[data-tip]').forEach(bar => {
  bar.addEventListener('mousemove', e => {
    tip.textContent = bar.dataset.tip;
    tip.style.display = 'block';
    tip.style.left = (e.clientX + 12) + 'px';
    tip.style.top = (e.clientY - 28) + 'px';
  });
  bar.addEventListener('mouseleave', () => { tip.style.display = 'none'; });
});

render();
</script>
</body>
</html>"""


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    signals = fetch_all_signals()
    html = build_html(signals)
    out_path = OUT_DIR / "intelligence_explorer.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"[OK] Dashboard: {out_path}")
    print(f"     {len(signals)} signals | {len(set(s['company'] for s in signals))} companies")


if __name__ == "__main__":
    main()
