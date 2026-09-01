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
          AND COALESCE(a.feed_type, 'competitor') = 'competitor'
          AND COALESCE(s.bullets, '') != ''
          AND UPPER(COALESCE(s.bullets, '')) NOT LIKE 'SKIP%'
        ORDER BY s.relevance_score DESC, a.created_at DESC
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
    seen_urls: set[str] = set()
    for src, title, url, tags, feed_type, created_at, summary, score in rows:
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

    high = sum(1 for s in signals if s["score"] == 3)
    n_firms = len({s["company"] for s in signals})

    deck = (
        f"{len(signals)} signals from {n_firms} firms in the last {WINDOW_WEEKS * 7} days — "
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
    columns, mx_rows = firm_theme_matrix(signals)

    all_tags = sorted({t for s in signals for t in s["tags"]})
    now = datetime.now(timezone.utc).strftime("%d %B %Y")
    edition_html = f"Edition {escape(EDITION)} · " if EDITION else ""
    demo_chip = f'<span class="demo-chip">{escape(DEMO_LABEL)}</span>' if DEMO_LABEL else ""

    tag_pills = "\n".join(
        f'<button class="pill" data-filter="tag" data-value="{escape(t)}">{escape(tag_label(t))}</button>'
        for t in all_tags
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
        "__MATRIX__": render_matrix(columns, mx_rows),
        "__TAG_PILLS__": tag_pills,
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

    /* ── Exhibit: matrix ── */
    .exhibit {
      padding: 26px 52px 28px;
      border-bottom: 1px solid var(--rule);
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

    /* ── Register ── */
    .register { padding: 4px 52px 44px; }

    .list-head {
      font-size: 12.5px;
      color: var(--ink-3);
      padding: 22px 0 8px;
      border-bottom: 1px solid var(--ink);
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
    <div class="masthead-meta">__EDITION__Generated __DATE__ · Last __WINDOW_DAYS__ days</div>
  </div>

  <div class="lede">
    <h1>__HEADLINE__</h1>
    <div class="deck">__DECK__</div>
  </div>

  <div class="exhibit">
    <div class="exhibit-title">Where competitors publish</div>
    <div class="matrix-scroll">
      __MATRIX__
    </div>
    <div class="exhibit-note">A signal may carry several themes. Darker cells = more signals.</div>
  </div>

  <div class="filters">
    <button class="pill active" data-filter="tag" data-value="all">All themes</button>
    __TAG_PILLS__
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

let filters = { tag: 'all', search: '' };

function escHtml(s) {
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function matches(s) {
  if (filters.tag !== 'all' && !s.tags.includes(filters.tag)) return false;
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
  return '<div class="row">' +
    '<div class="row-meta">' + star + '<span class="firm">' + escHtml(s.company) + '</span>' + dom + cw + '</div>' +
    '<a class="row-title" href="' + escHtml(s.url) + '" target="_blank" rel="noopener">' +
      escHtml(s.title) + '</a>' +
    '<div class="row-sum">' + escHtml(s.summary || '') + '</div>' +
  '</div>';
}

function sortSignals(list) {
  return list.slice().sort((a, b) => (b.score - a.score) || (a.created_at < b.created_at ? 1 : -1));
}

function render() {
  const el = document.getElementById('register');
  const visible = sortSignals(SIGNALS.filter(matches));

  if (!visible.length) {
    el.innerHTML = '<div class="empty-note">No signals match the current filters.</div>';
    return;
  }

  const label = visible.length + ' signal' + (visible.length !== 1 ? 's' : '') + ' · ranked by relevance · ★ = high';
  el.innerHTML =
    '<div class="list-head">' + label + '</div>' +
    visible.map(rowHtml).join('');
}

document.querySelectorAll('.pill[data-filter]').forEach(pill => {
  pill.addEventListener('click', () => {
    document.querySelectorAll('.pill[data-filter="tag"]').forEach(p => p.classList.remove('active'));
    pill.classList.add('active');
    filters.tag = pill.dataset.value;
    render();
  });
});

document.getElementById('search').addEventListener('input', e => {
  filters.search = e.target.value.trim();
  render();
});

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    filters = { tag: 'all', search: '' };
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
