# generate_dashboard.py — Intelligence Explorer v3 (consulting-exhibit edition)
from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from urllib.parse import urlparse

DB_PATH = os.getenv("INTEL_DB_PATH", "intel.db")
SOURCES_PATH = os.getenv("INTEL_SOURCES_PATH", "sources.json")
OUT_DIR = Path(os.getenv("INTEL_OUT_DIR", "output"))
WINDOW_WEEKS = int(os.getenv("INTEL_DASHBOARD_WEEKS", "4"))
EDITION = os.getenv("INTEL_EDITION", "")

# Branding — all optional, so the public repo ships with neutral defaults.
BRAND = os.getenv("INTEL_BRAND", "Competitor Intelligence")
OWNER_NAME = os.getenv("INTEL_OWNER_NAME", "").strip()
OWNER_TITLE = os.getenv("INTEL_OWNER_TITLE", "").strip()
OWNER_EMAIL = os.getenv("INTEL_OWNER_EMAIL", "").strip()
OWNER_URL = os.getenv("INTEL_OWNER_URL", "").strip()
DEMO_LABEL = os.getenv("INTEL_DEMO_LABEL", "").strip()

# Fixed period label (e.g. "July - August 2026") replaces the rolling
# "Last N days" wording so a published snapshot stays truthful as it ages.
PERIOD_LABEL = os.getenv("INTEL_PERIOD_LABEL", "").strip()

# Social-card metadata for a publicly hosted dashboard (absolute URLs).
OG_IMAGE = os.getenv("INTEL_OG_IMAGE", "").strip()
OG_URL = os.getenv("INTEL_OG_URL", "").strip()

# Themes follow the CFO-agenda pillars: strategy, delivery (GBS/GCC),
# steering (Controlling & FP&A), with agentic AI as the cross-cutting layer.
TAG_LABELS = {
    "Finance_Strategy": "Finance strategy",
    "GBS": "GBS",
    "GCC": "GCC",
    "Controlling_FPA": "Controlling & FP&A",
    "Agentic_AI": "Agentic AI",
    "Operating_Model": "Operating model",
    "Analyst_Research": "Analyst research",
}
CLUSTER_ORDER = ["MBB", "Big4", "Accenture", "Analysts", "Other"]

# Firm logos are rendered as favicons from the firm's own domain.
# Extend or override via a "firm_domains" object in sources.json.
FIRM_DOMAINS = {
    "mckinsey": "mckinsey.com",
    "bcg": "bcg.com",
    "bain": "bain.com",
    "deloitte": "deloitte.com",
    "ey": "ey.com",
    "kpmg": "kpmg.com",
    "pwc": "pwc.com",
    "accenture": "accenture.com",
    "hfs": "hfsresearch.com",
    "everest": "everestgrp.com",
    "sson": "ssonetwork.com",
    "gartner": "gartner.com",
}

# Domains whose favicon the icon services don't have — embed their icon
# directly (mckinsey.com blocks non-browser requests, so a hotlink is
# unreliable; this is their favicon downscaled to 32px).
FIRM_ICON_OVERRIDES = {
    "mckinsey.com": "data:image/png;base64,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",
}


def firm_icon_url(domain: str) -> str:
    if not domain:
        return ""
    return FIRM_ICON_OVERRIDES.get(
        domain, f"https://www.google.com/s2/favicons?domain={domain}&sz=32"
    )


def favicon_img(icon: str, size_px: int = 14, cls: str = "favicon") -> str:
    if not icon:
        return ""
    return (
        f'<img class="{cls}" src="{escape(icon)}" '
        f'alt="" width="{size_px}" height="{size_px}" loading="lazy">'
    )

# Sequential single-hue ramp (light -> dark) for the firm x theme matrix.
HEAT_RAMP = ["#F1F5FA", "#D9E4F0", "#B3C9E1", "#82A6CB", "#4F7BAA", "#27568C"]


def tag_label(tag: str) -> str:
    return TAG_LABELS.get(tag, tag.replace("_", " "))


def fetch_all_signals() -> list[dict]:
    start = (datetime.now(timezone.utc) - timedelta(weeks=WINDOW_WEEKS)).isoformat()
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    # Older databases may predate the signal_type column.
    try:
        cur.execute("ALTER TABLE article_summaries ADD COLUMN signal_type TEXT DEFAULT ''")
        con.commit()
    except Exception:
        pass
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
            COALESCE(s.relevance_score, 2) as relevance_score,
            COALESCE(s.signal_type, '') as signal_type
        FROM articles a
        LEFT JOIN article_summaries s ON s.article_id = a.article_id
        WHERE a.created_at >= ?
          AND COALESCE(a.feed_type, 'competitor') IN ('competitor', 'analyst')
          AND COALESCE(s.bullets, '') != ''
          AND UPPER(COALESCE(s.bullets, '')) NOT LIKE 'SKIP%'
        ORDER BY s.relevance_score DESC, a.created_at DESC
        """,
        (start,),
    )
    rows = cur.fetchall()
    con.close()

    # Load firm clusters (and optional logo domains) from sources.json
    firm_domains = dict(FIRM_DOMAINS)
    try:
        with open(SOURCES_PATH, encoding="utf-8") as cf:
            scfg = json.load(cf)
        firm_clusters = scfg.get("firm_clusters", {})
        company_to_cluster = {}
        for cluster, firms in firm_clusters.items():
            for firm in firms:
                company_to_cluster[firm.lower()] = cluster
        for firm, dom in scfg.get("firm_domains", {}).items():
            if not firm.startswith("_") and isinstance(dom, str):
                firm_domains[firm.lower()] = dom
    except Exception:
        company_to_cluster = {}

    signals = []
    seen_urls: set[str] = set()
    for src, title, url, tags, feed_type, created_at, summary, score, signal_type in rows:
        # The same article often arrives through several alert feeds —
        # keep only the first (highest-scored) occurrence per URL.
        clean = (url or "").strip()
        if clean and clean in seen_urls:
            continue
        if clean:
            seen_urls.add(clean)

        parts = (src or "Unknown").split("_", 1)
        company = parts[0].strip()
        topic = parts[1].replace("_", "/") if len(parts) > 1 else ""

        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            cw = f"CW {dt.strftime('%V')}"
        except Exception:
            cw = ""

        tag_list = [t.strip() for t in tags.split(",") if t.strip() and t.strip() != "Client_Signal"]
        cluster = company_to_cluster.get(company.lower(), "Other")

        try:
            domain = urlparse(url or "").netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
        except Exception:
            domain = ""

        signals.append({
            "domain": domain,
            "icon_url": firm_icon_url(firm_domains.get(company.lower(), "")),
            "source": src,
            "company": company,
            "topic": topic,
            "title": title or "(no title)",
            "url": url or "#",
            "tags": tag_list,
            "feed_type": feed_type,
            "created_at": created_at,
            "cw": cw,
            "summary": summary,
            "score": int(score),
            "signal_type": (signal_type or "").strip().lower(),
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

def firm_theme_matrix(signals: list[dict]) -> tuple[list[str], list[dict]]:
    """Competitor and analyst signals: rows = firms (grouped by cluster), cols = themes."""
    comp = [s for s in signals if s["feed_type"] in ("competitor", "analyst")]
    col_counter: Counter[str] = Counter(t for s in comp for t in s["tags"])
    columns = [t for t in TAG_LABELS if t in col_counter]

    cells: dict[str, Counter] = {}
    clusters: dict[str, str] = {}
    icons: dict[str, str] = {}
    for s in comp:
        firm = s["company"]
        clusters[firm] = s["cluster"]
        icons[firm] = s.get("icon_url", "")
        c = cells.setdefault(firm, Counter())
        for t in s["tags"]:
            if t in columns:
                c[t] += 1

    rows = []
    for firm, counter in cells.items():
        rows.append({
            "firm": firm,
            "icon_url": icons.get(firm, ""),
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


def weekly_series(signals: list[dict]) -> list[tuple[str, int]]:
    """New signals per ISO calendar week across the reporting window."""
    now = datetime.now(timezone.utc)
    monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    starts = [monday - timedelta(weeks=i) for i in range(WINDOW_WEEKS - 1, -1, -1)]

    counts = []
    for start in starts:
        end = start + timedelta(weeks=1)
        n = 0
        for s in signals:
            try:
                dt = datetime.fromisoformat(s["created_at"].replace("Z", "+00:00"))
            except Exception:
                continue
            if start <= dt < end:
                n += 1
        counts.append((f"CW {start.strftime('%V')}", n))
    return counts


def momentum_title(counts: list[tuple[str, int]]) -> str:
    """Action title for the signal-flow exhibit, derived purely from the counts."""
    vals = [n for _, n in counts]
    total = sum(vals)
    if not total:
        return "No signal flow in the window"
    if len(vals) >= 4:
        half = len(vals) // 2
        first = sum(vals[:half]) / half
        last = sum(vals[half:]) / (len(vals) - half)
        if first and last >= first * 1.4:
            return "Publishing has accelerated in the recent weeks of the window"
        if last <= first * 0.6:
            peak_label = max(counts, key=lambda c: c[1])[0]
            return f"Publishing has slowed since its {peak_label} peak"
    per_week = total / len(vals)
    return (
        f"Publishing runs at roughly {per_week:.0f} signal"
        f"{'s' if round(per_week) != 1 else ''} per week"
    )


def matrix_action_title(columns: list[str], rows: list[dict]) -> str:
    """Action title for the firm x theme exhibit, derived purely from the matrix."""
    total = sum(r["total"] for r in rows)
    if not total or not columns:
        return "No competitor publishing in the window"
    col_totals = [
        (c, sum(r["counts"][i] for r in rows)) for i, c in enumerate(columns)
    ]
    top_col, top_n = max(col_totals, key=lambda x: x[1])
    return (
        f"{tag_label(top_col)} draws {top_n} of {total} theme mentions "
        f"across {len(rows)} firms"
    )


def compute_headline(signals: list[dict]) -> tuple[str, str]:
    """Answer-first action title + supporting deck line, derived purely from the data."""
    if not signals:
        return (
            "No new signals in the reporting window",
            "The pipeline ran, but no articles cleared the relevance filters. "
            "Check feed configuration or widen the window.",
        )

    high = sum(1 for s in signals if s["score"] == 3)
    n_firms = len({s["company"] for s in signals})

    deck = (
        f"{len(signals)} signals from {n_firms} firms in "
        + (PERIOD_LABEL if PERIOD_LABEL else f"the last {WINDOW_WEEKS * 7} days")
        + " — "
        f"{high} rated high relevance."
    )

    theme_counts = Counter(t for s in signals for t in s["tags"])
    firm_counts = Counter(s["company"] for s in signals)
    top_firm, n_firm = firm_counts.most_common(1)[0]
    if theme_counts:
        top_theme, _ = theme_counts.most_common(1)[0]
        headline = (
            f"{tag_label(top_theme)} leads competitor publishing; "
            f"{top_firm} most active with {n_firm} signal{'s' if n_firm != 1 else ''}"
        )
        return headline, deck
    return f"{top_firm} drives competitor activity with {n_firm} signal{'s' if n_firm != 1 else ''}", deck


# ---------------------------------------------------------------- rendering

def render_matrix(columns: list[str], rows: list[dict]) -> str:
    if not rows:
        return '<div class="empty-note">No competitor signals in the window.</div>'

    max_cell = max((max(r["counts"]) for r in rows if r["counts"]), default=1) or 1

    head = "".join(
        f'<th class="mx-col mx-click" data-tag="{escape(c)}" tabindex="0" role="button" '
        f'title="Filter the register: {escape(tag_label(c))}">{escape(tag_label(c))}</th>'
        for c in columns
    )
    body_rows = []
    prev_cluster = None
    for r in rows:
        cluster_cell = ""
        if r["cluster"] != prev_cluster:
            span = sum(1 for x in rows if x["cluster"] == r["cluster"])
            cluster_cell = f'<td class="mx-cluster" rowspan="{span}">{escape(r["cluster"])}</td>'
            prev_cluster = r["cluster"]
        cells = []
        for i, c in enumerate(r["counts"]):
            if c == 0:
                cells.append('<td class="mx-cell mx-zero">·</td>')
            else:
                step = min(len(HEAT_RAMP) - 1, max(1, round(c / max_cell * (len(HEAT_RAMP) - 1))))
                color = HEAT_RAMP[step]
                ink = "#FFFFFF" if step >= 3 else "#1A1E26"
                tag = columns[i]
                tip = (
                    f"{r['firm']} × {tag_label(tag)} — {c} signal{'s' if c != 1 else ''}. "
                    "Click to filter the register."
                )
                cells.append(
                    f'<td class="mx-cell mx-click" data-firm="{escape(r["firm"])}" '
                    f'data-tag="{escape(tag)}" tabindex="0" role="button" '
                    f'title="{escape(tip)}" style="background:{color}; color:{ink};">{c}</td>'
                )
        icon = favicon_img(r.get("icon_url", ""), 14)
        firm_tip = f"Filter the register: {r['firm']}"
        body_rows.append(
            f'<tr>{cluster_cell}<td class="mx-firm mx-click" data-firm="{escape(r["firm"])}" '
            f'tabindex="0" role="button" title="{escape(firm_tip)}">{icon}{escape(r["firm"])}</td>'
            f'{"".join(cells)}<td class="mx-total">{r["total"]}</td></tr>'
        )
    return (
        '<table class="matrix"><thead><tr><th></th><th></th>'
        + head + '<th class="mx-col">Total</th></tr></thead><tbody>'
        + "".join(body_rows) + "</tbody></table>"
    )


def render_weekly(counts: list[tuple[str, int]]) -> str:
    """Compact bar strip: new signals per calendar week."""
    if not counts or not any(n for _, n in counts):
        return ""
    peak = max(n for _, n in counts)
    bars = []
    for i, (label, n) in enumerate(counts):
        h = max(3, round(n / peak * 56)) if n else 3
        cls = "bar" if n else "bar zero"
        tip = f"{label} — {n} new signal{'s' if n != 1 else ''}"
        # Direct-label peak weeks and the current week only.
        show_n = n and (n == peak or i == len(counts) - 1)
        val = f'<div class="wk-n">{n}</div>' if show_n else ""
        bars.append(
            f'<div class="wk" title="{escape(tip)}">{val}'
            f'<div class="{cls}" style="height:{h}px"></div>'
            f'<div class="wk-l">{escape(label.replace("CW ", ""))}</div></div>'
        )
    return (
        '<div class="spark" role="img" aria-label="New signals per calendar week">'
        + "".join(bars)
        + '</div><div class="spark-axis">Calendar week</div>'
    )


def render_exhibit2(counts: list[tuple[str, int]]) -> str:
    strip = render_weekly(counts)
    if not strip:
        return ""
    return (
        '<div class="exhibit">'
        '<div class="exhibit-kicker">Exhibit 2 · Signal flow</div>'
        f'<div class="exhibit-title">{escape(momentum_title(counts))}</div>'
        f'{strip}'
        '<div class="exhibit-note">New signals per calendar week; hover a bar for the count.</div>'
        "</div>"
    )


def render_footer() -> str:
    if OWNER_NAME:
        photo = embed_photo()
        title_html = f'<div class="foot-role">{escape(OWNER_TITLE)}</div>' if OWNER_TITLE else ""
        email_html = (
            f'<a class="foot-mail" href="mailto:{escape(OWNER_EMAIL)}">{escape(OWNER_EMAIL)}</a>'
            if OWNER_EMAIL else ""
        )
        link_label = urlparse(OWNER_URL).netloc or OWNER_URL
        link_html = (
            f'<a class="foot-mail" href="{escape(OWNER_URL)}">{escape(link_label)}</a>'
            if OWNER_URL else ""
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
    columns, mx_rows = firm_theme_matrix(signals)
    week_counts = weekly_series(signals)

    all_tags = sorted({t for s in signals for t in s["tags"]})
    now = datetime.now(timezone.utc).strftime("%d %B %Y")
    edition_html = f"Edition {escape(EDITION)} · " if EDITION else ""
    demo_chip = f'<span class="demo-chip">{escape(DEMO_LABEL)}</span>' if DEMO_LABEL else ""

    tag_pills = "\n".join(
        f'<button class="pill" data-filter="tag" data-value="{escape(t)}">{escape(tag_label(t))}</button>'
        for t in all_tags
    )

    html = HTML_TEMPLATE
    og_lines = []
    if OG_IMAGE:
        og_lines.append(f'\n  <meta property="og:image" content="{escape(OG_IMAGE)}">')
        og_lines.append(f'\n  <meta name="twitter:card" content="summary_large_image">')
        og_lines.append(f'\n  <meta name="twitter:image" content="{escape(OG_IMAGE)}">')
    if OG_URL:
        og_lines.append(f'\n  <meta property="og:url" content="{escape(OG_URL)}">')
    og_extra = "".join(og_lines)

    replacements = {
        "__BRAND__": escape(BRAND),
        "__EDITION__": edition_html,
        "__DEMO_CHIP__": demo_chip,
        "__DATE__": now,
        "__WINDOW_DAYS__": str(WINDOW_WEEKS * 7),
        "__HEADLINE__": escape(headline),
        "__DECK__": escape(deck),
        "__MATRIX_TITLE__": escape(matrix_action_title(columns, mx_rows)),
        "__MATRIX__": render_matrix(columns, mx_rows),
        "__N_SIGNALS__": str(len(signals)),
        "__EXHIBIT2__": render_exhibit2(week_counts),
        "__TAG_PILLS__": tag_pills,
        "__FOOTER_IDENTITY__": render_footer(),
        "__SIGNALS_JSON__": signals_json,
        "__WINDOW_LABEL__": escape(PERIOD_LABEL) if PERIOD_LABEL else f"Last {WINDOW_WEEKS * 7} days",
        "__OG_EXTRA__": og_extra,
        "__TAG_LABELS_JSON__": json.dumps(TAG_LABELS, ensure_ascii=False),
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
  <meta name="description" content="__BRAND__ — weekly competitor and analyst signals, scored for relevance and summarised automatically. Firm-by-theme exhibit, signal flow, and a filterable register.">
  <meta property="og:title" content="__BRAND__ — Intelligence Explorer">
  <meta property="og:description" content="Weekly competitor and analyst signals, scored for relevance and summarised automatically.">
  <meta property="og:type" content="website">__OG_EXTRA__
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
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
      --serif: 'Source Serif 4', Georgia, serif;
      --sans: 'IBM Plex Sans', 'Helvetica Neue', Arial, sans-serif;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    html { background: var(--stock); }
    body {
      font-family: var(--sans);
      color: var(--ink);
      line-height: 1.55;
      background: var(--stock);
      -webkit-font-smoothing: antialiased;
    }

    .page {
      max-width: 880px;
      margin: 0 auto;
      background: var(--paper);
      min-height: 100vh;
      border-left: 1px solid var(--rule);
      border-right: 1px solid var(--rule);
    }

    /* ── Masthead ── */
    .masthead {
      padding: 30px 52px 0;
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 16px;
      flex-wrap: wrap;
    }
    .brand {
      font-size: 13px;
      font-weight: 600;
      color: var(--ink);
    }
    .masthead-meta {
      font-size: 12.5px;
      color: var(--ink-3);
    }
    .demo-chip {
      display: inline-block;
      font-size: 11px;
      font-weight: 500;
      color: var(--ink-2);
      border: 1px solid var(--rule);
      padding: 0 7px;
      border-radius: 2px;
      margin-left: 8px;
      vertical-align: 1px;
    }

    /* ── Headline (the answer) ── */
    .lede {
      padding: 12px 52px 26px;
      border-bottom: 1px solid var(--ink);
    }
    .lede h1 {
      font-family: var(--serif);
      font-size: clamp(26px, 4vw, 34px);
      font-weight: 600;
      line-height: 1.22;
      letter-spacing: -0.3px;
    }
    .lede .deck {
      margin-top: 10px;
      font-size: 15.5px;
      color: var(--ink-2);
      max-width: 42em;
    }

    /* ── Exhibits ── */
    .exhibit {
      padding: 24px 52px 28px;
      border-bottom: 1px solid var(--rule);
    }
    .exhibit-kicker {
      font-size: 11.5px;
      font-weight: 600;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--ink-3);
      margin-bottom: 6px;
    }
    .exhibit-title {
      font-family: var(--serif);
      font-size: 19px;
      font-weight: 600;
      margin-bottom: 16px;
    }
    .matrix-scroll { overflow-x: auto; }
    .matrix { border-collapse: separate; border-spacing: 2px; width: 100%; }
    .matrix th {
      font-size: 12px;
      color: var(--ink-2);
      font-weight: 500;
      text-align: center;
      padding: 0 6px 6px;
      white-space: nowrap;
    }
    .mx-cluster {
      font-size: 11.5px;
      font-weight: 600;
      color: var(--ink-3);
      vertical-align: top;
      padding: 6px 12px 0 0;
      white-space: nowrap;
    }
    .mx-firm {
      font-size: 14px;
      padding: 4px 12px 4px 0;
      white-space: nowrap;
    }
    .favicon {
      width: 14px; height: 14px;
      border-radius: 3px;
      vertical-align: -2px;
      margin-right: 7px;
    }
    .mx-cell {
      font-size: 13px;
      text-align: center;
      min-width: 46px;
      padding: 6px 0;
      border-radius: 2px;
    }
    .mx-zero { color: var(--rule); background: transparent; }
    .mx-total {
      font-size: 13px;
      font-weight: 600;
      text-align: center;
      color: var(--ink-2);
      padding: 6px 0 6px 8px;
    }
    .exhibit-note {
      font-size: 12.5px;
      color: var(--ink-3);
      margin-top: 12px;
    }

    /* Matrix cross-filtering */
    .mx-click { cursor: pointer; }
    th.mx-click:hover, td.mx-firm.mx-click:hover { color: var(--accent); }
    td.mx-cell.mx-click:hover { outline: 1.5px solid var(--ink-2); outline-offset: -1.5px; }
    .mx-click.sel { outline: 2px solid var(--ink); outline-offset: -2px; }
    th.mx-click.sel, td.mx-firm.mx-click.sel { outline: none; color: var(--ink); text-decoration: underline; text-underline-offset: 3px; }

    /* ── Exhibit: signal flow ── */
    .spark {
      display: flex;
      align-items: flex-end;
      gap: 8px;
      height: 92px;
      margin-top: 4px;
    }
    .wk {
      flex: 0 0 34px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: flex-end;
      height: 100%;
    }
    .wk .bar {
      width: 20px;
      background: var(--accent);
      border-radius: 2px 2px 0 0;
    }
    .wk .bar.zero { background: var(--rule-soft); border-radius: 1px; }
    .wk:hover .bar { opacity: 0.8; }
    .wk-n { font-size: 11.5px; color: var(--ink-2); margin-bottom: 4px; font-weight: 500; }
    .wk-l { font-size: 10.5px; color: var(--ink-3); margin-top: 6px; }
    .spark-axis { font-size: 10.5px; color: var(--ink-3); margin-top: 2px; }

    /* ── Filters ── */
    .filters {
      padding: 14px 52px 0;
      display: flex;
      gap: 0 22px;
      flex-wrap: wrap;
      align-items: baseline;
      border-bottom: 1px solid var(--rule);
      position: sticky;
      top: 0;
      background: rgba(255,255,255,0.97);
      z-index: 40;
    }
    .pill {
      font-family: var(--sans);
      font-size: 13.5px;
      padding: 6px 1px 11px;
      border: none;
      border-bottom: 2px solid transparent;
      background: none;
      color: var(--ink-3);
      cursor: pointer;
    }
    .pill:hover { color: var(--ink); }
    .pill.active {
      color: var(--ink);
      font-weight: 600;
      border-bottom-color: var(--ink);
    }
    .search-input {
      margin-left: auto;
      flex: 0 1 200px;
      min-width: 140px;
      font-family: var(--sans);
      font-size: 13.5px;
      padding: 6px 1px 10px;
      border: none;
      border-bottom: 1px solid var(--rule);
      color: var(--ink);
      background: none;
      outline: none;
    }
    .search-input:focus { border-bottom-color: var(--ink); }
    .pill-sep {
      align-self: center;
      width: 1px;
      height: 16px;
      background: var(--rule);
    }
    .chip {
      font-family: var(--sans);
      font-size: 12.5px;
      align-self: center;
      color: var(--ink);
      background: none;
      border: 1px solid var(--rule);
      border-radius: 2px;
      padding: 2px 8px;
      margin-bottom: 4px;
      cursor: pointer;
      white-space: nowrap;
    }
    .chip:hover { border-color: var(--ink-2); }
    .chip .x { color: var(--ink-3); margin-left: 6px; }

    /* ── Register ── */
    .register { padding: 4px 52px 44px; }

    .list-head {
      font-size: 12.5px;
      color: var(--ink-3);
      padding: 22px 0 8px;
      border-bottom: 1px solid var(--ink);
    }

    .group-label {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      font-family: var(--serif);
      font-size: 16px;
      font-weight: 600;
      color: var(--ink);
      padding: 26px 0 7px;
      border-bottom: 1px solid var(--rule);
    }
    .group-label .count { font-family: var(--sans); font-size: 12px; font-weight: 400; color: var(--ink-3); }
    .group-sub {
      font-size: 12.5px;
      color: var(--ink-3);
      padding: 4px 0 2px;
    }

    .row {
      padding: 16px 0 18px;
      border-bottom: 1px solid var(--rule-soft);
    }
    .row-meta {
      font-size: 12.5px;
      color: var(--ink-3);
      margin-bottom: 3px;
    }
    .row-meta .firm { color: var(--ink-2); font-weight: 600; }
    .row-meta .star { color: var(--accent); }
    .row-title {
      display: inline-block;
      font-family: var(--serif);
      font-size: 17px;
      font-weight: 600;
      line-height: 1.35;
      color: var(--ink);
      text-decoration: none;
    }
    .row-title:hover { color: var(--accent); text-decoration: underline; }
    .row-sum {
      margin-top: 5px;
      font-size: 14px;
      line-height: 1.6;
      color: var(--ink-2);
      max-width: 44em;
    }

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
      padding: 22px 52px 30px;
      display: flex;
      justify-content: space-between;
      gap: 24px;
      align-items: flex-start;
    }
    .foot-owner { display: flex; gap: 12px; align-items: center; }
    .foot-name { font-size: 13.5px; font-weight: 600; }
    .foot-role { font-size: 12px; color: var(--ink-2); }
    .foot-mail { font-size: 12px; color: var(--accent); text-decoration: none; }
    .foot-method {
      font-size: 11.5px;
      color: var(--ink-3);
      text-align: right;
      max-width: 40em;
      line-height: 1.6;
    }

    /* ── Responsive ── */
    @media (max-width: 860px) {
      .masthead, .lede, .exhibit, .filters, .register, .foot { padding-left: 22px; padding-right: 22px; }
      .foot { flex-direction: column; }
      .foot-method { text-align: left; }
    }

    @media print {
      html, body { background: #fff; }
      .page { border: none; max-width: none; }
      .filters { display: none; }
      .row { break-inside: avoid; }
    }
  </style>
</head>
<body>
<div class="page">

  <div class="masthead">
    <div class="brand">__BRAND__ __DEMO_CHIP__</div>
    <div class="masthead-meta">__EDITION__Generated __DATE__ · __WINDOW_LABEL__</div>
  </div>

  <div class="lede">
    <h1>__HEADLINE__</h1>
    <div class="deck">__DECK__</div>
  </div>

  <div class="exhibit">
    <div class="exhibit-kicker">Exhibit 1 · Where competitors publish</div>
    <div class="exhibit-title">__MATRIX_TITLE__</div>
    <div class="matrix-scroll">
      __MATRIX__
    </div>
    <div class="exhibit-note">n = __N_SIGNALS__ signals; a signal may carry several themes. Darker cells = more signals. Click a firm, theme, or cell to filter the register below.</div>
  </div>

  __EXHIBIT2__

  <div class="filters">
    <button class="pill active" data-filter="tag" data-value="all">All themes</button>
    __TAG_PILLS__
    <span class="pill-sep" aria-hidden="true"></span>
    <button class="pill" data-filter="type" data-value="move">Market moves</button>
    <button class="pill" data-filter="type" data-value="research">Research</button>
    <button class="chip" id="firmChip" hidden></button>
    <input class="search-input" id="search" type="text" placeholder="Search&hellip;">
  </div>

  <div class="register" id="register"></div>

  <div class="foot">
    __FOOTER_IDENTITY__
    <div class="foot-method">
      Public sources via Google Alerts RSS · relevance scored and summarised by Claude ·
      summaries are AI-generated — verify against the source before use.
    </div>
  </div>

</div>

<script>
const SIGNALS = __SIGNALS_JSON__;
const TAG_LABELS = __TAG_LABELS_JSON__;

let filters = { tag: 'all', type: 'all', firm: 'all', search: '' };

function escHtml(s) {
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function matches(s) {
  if (filters.tag !== 'all' && !s.tags.includes(filters.tag)) return false;
  if (filters.firm !== 'all' && s.company !== filters.firm) return false;
  if (filters.type !== 'all' && signalType(s) !== filters.type) return false;
  if (filters.search) {
    const q = filters.search.toLowerCase();
    if (!(s.title + ' ' + s.summary + ' ' + s.company + ' ' + s.topic).toLowerCase().includes(q)) return false;
  }
  return true;
}

function rowHtml(s) {
  const star = s.score === 3 ? '<span class="star" title="High relevance">★</span> ' : '';
  const dom = s.domain ? ' · ' + escHtml(s.domain) : '';
  const cw = s.cw ? ' · ' + escHtml(s.cw) : '';
  const icon = s.icon_url
    ? '<img class="favicon" src="' + escHtml(s.icon_url) + '" alt="" width="14" height="14" loading="lazy">'
    : '';
  return '<div class="row">' +
    '<div class="row-meta">' + star + icon + '<span class="firm">' + escHtml(s.company) + '</span>' + dom + cw + '</div>' +
    '<a class="row-title" href="' + escHtml(s.url) + '" target="_blank" rel="noopener">' +
      escHtml(s.title) + '</a>' +
    '<div class="row-sum">' + escHtml(s.summary || '') + '</div>' +
  '</div>';
}

function sortSignals(list) {
  return list.slice().sort((a, b) => (b.score - a.score) || (a.created_at < b.created_at ? 1 : -1));
}

const MOVE_HINT = /\b(launch|launches|announces?|acquir|invest|alliance|partner|unveil|introduc|recogni[sz]ed|leader in|expands?|wins?)\b/i;

function signalType(s) {
  if (s.signal_type === 'move' || s.signal_type === 'research') return s.signal_type;
  return MOVE_HINT.test(s.title) ? 'move' : 'research';
}

function groupHtml(title, sub, items) {
  if (!items.length) return '';
  return '<div class="group-label"><span>' + title + '</span><span class="count">' + items.length + '</span></div>' +
    '<div class="group-sub">' + sub + '</div>' +
    items.map(rowHtml).join('');
}

function render() {
  const el = document.getElementById('register');
  const visible = sortSignals(SIGNALS.filter(matches));

  if (!visible.length) {
    el.innerHTML = '<div class="empty-note">No signals match the current filters.</div>';
    return;
  }

  const moves = visible.filter(s => signalType(s) === 'move');
  const research = visible.filter(s => signalType(s) === 'research');

  const parts = [visible.length + ' signal' + (visible.length !== 1 ? 's' : '')];
  if (filters.firm !== 'all') parts.push(escHtml(filters.firm));
  if (filters.tag !== 'all') parts.push(escHtml(TAG_LABELS[filters.tag] || filters.tag));
  if (filters.type !== 'all') parts.push(filters.type === 'move' ? 'market moves' : 'research');
  parts.push('ranked by relevance · ★ = high');
  const label = parts.join(' · ');
  el.innerHTML =
    '<div class="list-head">' + label + '</div>' +
    groupHtml('Market moves', 'Offerings, alliances, M&amp;A, positioning — moves that may demand a competitive response.', moves) +
    groupHtml('Research &amp; viewpoints', 'Surveys, reports, and thought leadership — to read, cite, and benchmark against.', research);
}

function syncControls() {
  // Theme pills mirror filters.tag; type pills toggle; the firm chip shows filters.firm.
  document.querySelectorAll('.pill[data-filter="tag"]').forEach(p =>
    p.classList.toggle('active', p.dataset.value === filters.tag));
  document.querySelectorAll('.pill[data-filter="type"]').forEach(p =>
    p.classList.toggle('active', p.dataset.value === filters.type));
  const chip = document.getElementById('firmChip');
  if (filters.firm !== 'all') {
    chip.innerHTML = escHtml(filters.firm) + '<span class="x">&times;</span>';
    chip.hidden = false;
  } else {
    chip.hidden = true;
  }
  // Matrix selection state.
  document.querySelectorAll('.mx-click').forEach(el => {
    const f = el.dataset.firm, t = el.dataset.tag;
    let sel;
    if (f && t) sel = filters.firm === f && filters.tag === t;
    else if (f) sel = filters.firm === f && filters.tag === 'all';
    else sel = filters.tag === t && filters.firm === 'all';
    el.classList.toggle('sel', sel);
  });
}

function apply(patch) {
  Object.assign(filters, patch);
  syncControls();
  render();
}

document.querySelectorAll('.pill[data-filter="tag"]').forEach(pill => {
  pill.addEventListener('click', () => apply({ tag: pill.dataset.value }));
});

document.querySelectorAll('.pill[data-filter="type"]').forEach(pill => {
  pill.addEventListener('click', () =>
    apply({ type: filters.type === pill.dataset.value ? 'all' : pill.dataset.value }));
});

document.getElementById('firmChip').addEventListener('click', () => apply({ firm: 'all' }));

document.querySelectorAll('.mx-click').forEach(el => {
  const activate = () => {
    const f = el.dataset.firm, t = el.dataset.tag;
    if (el.classList.contains('sel')) {
      apply({ firm: 'all', tag: 'all' });
    } else {
      apply({ firm: f || 'all', tag: t || 'all' });
    }
  };
  el.addEventListener('click', activate);
  el.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(); }
  });
});

document.getElementById('search').addEventListener('input', e => {
  filters.search = e.target.value.trim();
  render();
});

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    document.getElementById('search').value = '';
    apply({ tag: 'all', type: 'all', firm: 'all', search: '' });
  }
  if (e.key === '/' && document.activeElement !== document.getElementById('search')) {
    e.preventDefault();
    document.getElementById('search').focus();
  }
});

syncControls();
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
