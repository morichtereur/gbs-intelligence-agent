# generate_dashboard.py — TLCA Intelligence Explorer v2
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = os.getenv("INTEL_DB_PATH", "intel.db")
OUT_DIR = Path(os.getenv("INTEL_OUT_DIR", "output"))
WINDOW_WEEKS = int(os.getenv("INTEL_DASHBOARD_WEEKS", "4"))


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
        with open("sources.json") as cf:
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
            cw = f"CW {dt.strftime('%V')} ({dt.strftime('%b %d')})"
            week_label = f"Week {dt.strftime('%V')}"
        except Exception:
            cw = "Unknown"
            week_label = "Unknown"

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
            "summary": summary,
            "score": int(score),
            "cluster": cluster,
        })

    return signals


def embed_photo() -> str:
    """Embed photo.jpg as base64 img tag, or return placeholder div."""
    import base64
    photo_path = Path(os.getenv("INTEL_PHOTO_PATH", "photo.jpg"))
    if photo_path.exists():
        with open(photo_path, "rb") as pf:
            img_b64 = base64.b64encode(pf.read()).decode("utf-8")
        ext = photo_path.suffix.lower().replace(".", "")
        mime = "jpeg" if ext in ("jpg", "jpeg") else ext
        return f'<img src="data:image/{mime};base64,{img_b64}" style="width:44px; height:44px; border-radius:50%; object-fit:cover; border:2px solid #2E2E42;">'
    return '<div style="width:44px; height:44px; border-radius:50%; background:#252535; border:2px solid #2E2E42;"></div>'


def build_html(signals: list[dict]) -> str:
    signals_json = json.dumps(signals, ensure_ascii=False)
    all_tags = sorted(set(t for s in signals for t in s["tags"]))
    all_weeks = sorted(set(s["week_label"] for s in signals), reverse=True)
    now = datetime.now(timezone.utc).strftime("%d %B %Y")
    photo_html = embed_photo()
    photo_html_footer = f'''<div style="padding:20px 40px; border-top:1px solid #252535; display:flex; align-items:center; justify-content:space-between; background:#15151C;">
  <div style="display:flex; align-items:center; gap:14px;">
    {photo_html}
    <div>
      <div style="font-size:13px; font-weight:600; color:#EEEEF5;">Your Name</div>
      <div style="font-size:11px; color:#7070A0; margin-top:2px;">Consultant &middot; Business Consulting Finance &middot; EY Z&uuml;rich</div>
      <a href="mailto:your@email.com" style="font-size:11px; color:#FFC72C; text-decoration:none;">your@email.com</a>
    </div>
  </div>
  <div style="font-size:10px; color:#353550; text-align:right;">TLCA Intelligence Explorer<br>Built &amp; maintained by Your Name</div>
</div>'''


    tag_pills_html = "\n".join(
        f'<div class="pill" data-filter="tag" data-value="{t}">'
        f'<span class="pill-dot" data-tag="{t}"></span>{t.replace("_", " ")}</div>'
        for t in all_tags
    )
    week_pills_html = "\n".join(
        f'<div class="pill" data-filter="week" data-value="{w}">{w}</div>'
        for w in all_weeks
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>TLCA Intelligence Explorer</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #0D0D12;
      --surface: #15151C;
      --surface2: #1C1C26;
      --surface3: #222230;
      --border: #252535;
      --border2: #2E2E42;
      --accent: #FFC72C;
      --accent-dim: rgba(255,199,44,0.12);
      --text: #EEEEF5;
      --text-muted: #7070A0;
      --text-dim: #353550;
      --competitor: #4A9EFF;
      --client: #00C9A7;
      --tag-gbs: #FF6B6B;
      --tag-gcc: #4A9EFF;
      --tag-ai: #A78BFA;
      --tag-om: #F59E0B;
      --tag-default: #6B7280;
      --modal-bg: rgba(8,8,14,0.92);
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: 'DM Sans', sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      overflow-x: hidden;
    }}

    /* ── HEADER ── */
    .header {{
      padding: 24px 40px 20px;
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      position: sticky;
      top: 0;
      background: rgba(13,13,18,0.95);
      backdrop-filter: blur(16px);
      z-index: 90;
    }}

    .header h1 {{
      font-family: 'DM Serif Display', serif;
      font-size: 24px;
      font-weight: 400;
      letter-spacing: -0.3px;
    }}

    .header h1 .hl {{ color: var(--accent); }}
    .header-sub {{ font-size: 11px; color: var(--text-muted); margin-top: 3px; font-weight: 300; }}

    .badge {{
      font-size: 11px;
      color: var(--text-muted);
      background: var(--surface2);
      border: 1px solid var(--border2);
      padding: 5px 12px;
      border-radius: 20px;
    }}
    .badge b {{ color: var(--accent); }}

    /* ── FILTERS ── */
    .filters {{
      padding: 16px 40px;
      border-bottom: 1px solid var(--border);
      display: flex;
      gap: 20px;
      flex-wrap: wrap;
      align-items: flex-start;
      background: var(--surface);
    }}

    .filter-group {{ display: flex; flex-direction: column; gap: 7px; }}

    .filter-label {{
      font-size: 9px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 1.2px;
      color: var(--text-dim);
    }}

    .filter-pills {{ display: flex; gap: 5px; flex-wrap: wrap; }}

    .pill {{
      display: flex;
      align-items: center;
      gap: 5px;
      padding: 4px 11px;
      border-radius: 20px;
      font-size: 11px;
      font-weight: 500;
      cursor: pointer;
      border: 1px solid var(--border2);
      background: var(--surface2);
      color: var(--text-muted);
      transition: all 0.12s ease;
      user-select: none;
    }}

    .pill:hover {{ border-color: var(--accent); color: var(--text); }}
    .pill.active {{ background: var(--accent); border-color: var(--accent); color: #000; font-weight: 700; }}

    .pill-dot {{
      width: 7px; height: 7px;
      border-radius: 50%;
      flex-shrink: 0;
    }}

    .search-wrap {{ flex: 1; min-width: 220px; }}

    .search-input {{
      width: 100%;
      background: var(--surface2);
      border: 1px solid var(--border2);
      border-radius: 8px;
      padding: 7px 14px;
      font-size: 12px;
      color: var(--text);
      font-family: 'DM Sans', sans-serif;
      outline: none;
      transition: border-color 0.12s;
    }}
    .search-input:focus {{ border-color: var(--accent); }}
    .search-input::placeholder {{ color: var(--text-dim); }}

    /* ── STATS BAR ── */
    .stats-bar {{
      padding: 10px 40px;
      display: flex;
      gap: 28px;
      border-bottom: 1px solid var(--border);
      align-items: center;
    }}

    .stat {{ display: flex; align-items: baseline; gap: 6px; font-size: 12px; color: var(--text-muted); }}
    .stat-num {{ font-size: 20px; font-weight: 600; color: var(--text); font-family: 'DM Serif Display', serif; line-height: 1; }}
    .stat-dot {{ width: 7px; height: 7px; border-radius: 50%; display: inline-block; margin-right: 2px; }}

    .kbd-hint {{
      margin-left: auto;
      font-size: 10px;
      color: var(--text-dim);
      display: flex;
      gap: 10px;
    }}
    .kbd {{
      background: var(--surface2);
      border: 1px solid var(--border2);
      border-radius: 4px;
      padding: 1px 6px;
      font-family: monospace;
      color: var(--text-muted);
    }}

    /* ── GRID ── */
    .grid {{
      padding: 28px 40px 60px;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 14px;
      align-items: start;
    }}

    /* ── SECTION DIVIDER ── */
    .section-divider {{
      grid-column: 1 / -1;
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 6px 0 2px;
    }}
    .section-divider-label {{
      font-size: 10px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 1px;
      white-space: nowrap;
    }}
    .section-divider-line {{ flex: 1; height: 1px; background: var(--border); }}

    /* ── CARD ── */
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
      transition: border-color 0.15s, transform 0.15s, box-shadow 0.15s;
      display: flex;
      flex-direction: column;
      cursor: pointer;
      opacity: 0;
      animation: fadeUp 0.25s ease forwards;
    }}

    @keyframes fadeUp {{
      from {{ opacity: 0; transform: translateY(10px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}

    .card:hover {{
      border-color: var(--border2);
      transform: translateY(-2px);
      box-shadow: 0 6px 24px rgba(0,0,0,0.5);
    }}

    .card:hover .card-title {{ color: var(--accent); }}

    .card-header {{
      padding: 11px 14px 9px;
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}

    .card-company {{
      font-size: 10px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.9px;
    }}
    .card-company.competitor {{ color: var(--competitor); }}
    .card-company.client {{ color: var(--client); }}

    .card-right {{ display: flex; align-items: center; gap: 6px; }}

    .card-topic {{
      font-size: 9px; color: var(--text-muted);
      background: var(--surface3); padding: 2px 6px; border-radius: 8px;
    }}
    .card-cw {{ font-size: 9px; color: var(--text-dim); }}

    .card-body {{ padding: 12px 14px; flex: 1; display: flex; flex-direction: column; gap: 8px; }}

    .card-title {{
      font-size: 13px; font-weight: 600;
      line-height: 1.45; color: var(--text);
      transition: color 0.12s;
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}

    .card-summary {{
      font-size: 11px; line-height: 1.65;
      color: var(--text-muted); font-weight: 300;
      display: -webkit-box;
      -webkit-line-clamp: 4;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}

    .card-tags {{ display: flex; gap: 4px; flex-wrap: wrap; margin-top: 2px; }}

    .tag {{
      font-size: 9px; padding: 2px 7px;
      border-radius: 8px; font-weight: 600;
      letter-spacing: 0.3px;
    }}

    .card-footer {{
      padding: 8px 14px 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}

    .read-btn {{
      display: inline-block; padding: 6px 12px;
      background: var(--accent); color: #000;
      font-size: 10px; font-weight: 700;
      border-radius: 5px; text-decoration: none;
      transition: opacity 0.12s;
    }}
    .read-btn:hover {{ opacity: 0.85; }}

    .expand-hint {{
      font-size: 10px; color: var(--text-dim);
    }}

    /* ── EMPTY ── */
    .empty {{
      grid-column: 1 / -1; text-align: center;
      padding: 80px; color: var(--text-muted);
    }}
    .empty h3 {{
      font-family: 'DM Serif Display', serif;
      font-size: 22px; color: var(--text-dim); margin-bottom: 6px;
    }}

    /* ── MODAL ── */
    .modal-overlay {{
      display: none;
      position: fixed; inset: 0;
      background: var(--modal-bg);
      z-index: 200;
      backdrop-filter: blur(8px);
      align-items: center;
      justify-content: center;
      padding: 40px;
    }}
    .modal-overlay.open {{ display: flex; }}

    .modal {{
      background: var(--surface);
      border: 1px solid var(--border2);
      border-radius: 14px;
      max-width: 680px;
      width: 100%;
      max-height: 80vh;
      overflow-y: auto;
      animation: modalIn 0.2s ease;
      position: relative;
    }}

    @keyframes modalIn {{
      from {{ opacity: 0; transform: scale(0.96) translateY(8px); }}
      to {{ opacity: 1; transform: scale(1) translateY(0); }}
    }}

    .modal-header {{
      padding: 20px 24px 16px;
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
      position: sticky;
      top: 0;
      background: var(--surface);
      z-index: 1;
    }}

    .modal-company {{
      font-size: 10px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 1px;
      margin-bottom: 6px;
    }}
    .modal-company.competitor {{ color: var(--competitor); }}
    .modal-company.client {{ color: var(--client); }}

    .modal-title {{
      font-family: 'DM Serif Display', serif;
      font-size: 20px; line-height: 1.35;
      color: var(--text); font-weight: 400;
    }}

    .modal-close {{
      background: var(--surface2);
      border: 1px solid var(--border2);
      border-radius: 6px;
      color: var(--text-muted);
      font-size: 16px;
      cursor: pointer;
      width: 32px; height: 32px;
      display: flex; align-items: center; justify-content: center;
      flex-shrink: 0;
      transition: all 0.12s;
    }}
    .modal-close:hover {{ color: var(--text); border-color: var(--accent); }}

    .modal-body {{ padding: 20px 24px; display: flex; flex-direction: column; gap: 16px; }}

    .modal-meta {{
      display: flex; gap: 8px; flex-wrap: wrap; align-items: center;
    }}
    .modal-meta-item {{
      font-size: 11px; color: var(--text-muted);
      background: var(--surface2); border: 1px solid var(--border);
      padding: 3px 9px; border-radius: 10px;
    }}

    .modal-summary {{
      font-size: 14px; line-height: 1.7;
      color: var(--text-muted); font-weight: 300;
      border-left: 2px solid var(--accent);
      padding-left: 16px;
    }}

    .modal-tags {{ display: flex; gap: 5px; flex-wrap: wrap; }}

    .modal-actions {{ display: flex; gap: 10px; }}

    .modal-btn-primary {{
      padding: 10px 20px;
      background: var(--accent); color: #000;
      font-size: 12px; font-weight: 700;
      border-radius: 7px; text-decoration: none;
      transition: opacity 0.12s;
    }}
    .modal-btn-primary:hover {{ opacity: 0.85; }}

    .modal-btn-secondary {{
      padding: 10px 20px;
      background: var(--surface2); color: var(--text-muted);
      font-size: 12px; font-weight: 500;
      border-radius: 7px; border: 1px solid var(--border2);
      cursor: pointer; transition: all 0.12s;
    }}
    .modal-btn-secondary:hover {{ color: var(--text); border-color: var(--accent); }}

    ::-webkit-scrollbar {{ width: 5px; }}
    ::-webkit-scrollbar-track {{ background: var(--bg); }}
    ::-webkit-scrollbar-thumb {{ background: var(--border2); border-radius: 3px; }}
  </style>
</head>
<body>

<div class="header">
  <div>
    <h1>TLCA <span class="hl">Intelligence</span> Explorer</h1>
    <div class="header-sub">Business Consulting Finance &middot; EY Z&uuml;rich &middot; Generated {now}</div>
  </div>
  <div class="badge">Last <b>{WINDOW_WEEKS * 7}</b> days</div>
</div>

<div class="filters">
  <div class="filter-group">
    <div class="filter-label">Type</div>
    <div class="filter-pills">
      <div class="pill active" data-filter="type" data-value="all">All</div>
      <div class="pill" data-filter="type" data-value="competitor">Competitor</div>
      <div class="pill" data-filter="type" data-value="client">Client</div>
    </div>
  </div>

  <div class="filter-group">
    <div class="filter-label">Topic</div>
    <div class="filter-pills">
      <div class="pill active" data-filter="tag" data-value="all">All</div>
      {tag_pills_html}
    </div>
  </div>

  <div class="filter-group">
    <div class="filter-label">Week</div>
    <div class="filter-pills">
      <div class="pill active" data-filter="week" data-value="all">All</div>
      {week_pills_html}
    </div>
  </div>

  <div class="filter-group search-wrap">
    <div class="filter-label">Search</div>
    <input class="search-input" id="search" type="text" placeholder="Search titles, summaries, companies...">
  </div>
</div>

<div class="stats-bar">
  <div class="stat">
    <span class="stat-num" id="stat-total">{len(signals)}</span>
    <span>signals</span>
  </div>
  <div class="stat">
    <span class="stat-dot" style="background:var(--competitor)"></span>
    <span class="stat-num" id="stat-comp">{sum(1 for s in signals if s['feed_type']=='competitor')}</span>
    <span>competitor</span>
  </div>
  <div class="stat">
    <span class="stat-dot" style="background:var(--client)"></span>
    <span class="stat-num" id="stat-client">{sum(1 for s in signals if s['feed_type']=='client')}</span>
    <span>client</span>
  </div>
  <div class="stat">
    <span class="stat-num">{len(set(s['company'] for s in signals))}</span>
    <span>companies</span>
  </div>
  <div class="kbd-hint">
    <span><span class="kbd">/</span> search</span>
    <span><span class="kbd">Esc</span> reset / close</span>
    <span><span class="kbd">click</span> expand</span>
  </div>
</div>

<div class="grid" id="grid"></div>

<!-- MODAL -->
<div class="modal-overlay" id="modal-overlay">
  <div class="modal" id="modal">
    <div class="modal-header">
      <div>
        <div class="modal-company" id="modal-company"></div>
        <div class="modal-title" id="modal-title"></div>
      </div>
      <button class="modal-close" id="modal-close">&times;</button>
    </div>
    <div class="modal-body">
      <div class="modal-meta" id="modal-meta"></div>
      <div class="modal-summary" id="modal-summary"></div>
      <div class="modal-tags" id="modal-tags"></div>
      <div class="modal-actions">
        <a class="modal-btn-primary" id="modal-link" href="#" target="_blank" rel="noopener">Read the source</a>
        <button class="modal-btn-secondary" id="modal-close2">Close</button>
      </div>
    </div>
  </div>
</div>

<script>
const SIGNALS = {signals_json};

const TAG_COLORS = {{
  'GBS':            {{ bg: 'rgba(255,107,107,0.15)', color: '#FF6B6B', border: 'rgba(255,107,107,0.3)' }},
  'GCC':            {{ bg: 'rgba(74,158,255,0.15)',  color: '#4A9EFF', border: 'rgba(74,158,255,0.3)' }},
  'Agentic_AI':     {{ bg: 'rgba(167,139,250,0.15)', color: '#A78BFA', border: 'rgba(167,139,250,0.3)' }},
  'Operating_Model':{{ bg: 'rgba(245,158,11,0.15)',  color: '#F59E0B', border: 'rgba(245,158,11,0.3)' }},
}};

const DOT_COLORS = {{
  'GBS': '#FF6B6B',
  'GCC': '#4A9EFF',
  'Agentic_AI': '#A78BFA',
  'Operating_Model': '#F59E0B',
}};

// Set pill dot colors
document.querySelectorAll('.pill-dot').forEach(dot => {{
  const tag = dot.dataset.tag;
  if (DOT_COLORS[tag]) dot.style.background = DOT_COLORS[tag];
}});

function tagStyle(tag) {{
  const c = TAG_COLORS[tag];
  if (c) return `background:${{c.bg}};color:${{c.color}};border:1px solid ${{c.border}};`;
  return 'background:rgba(107,114,128,0.15);color:#9CA3AF;border:1px solid rgba(107,114,128,0.3);';
}}

let activeFilters = {{ type: 'all', tag: 'all', week: 'all', search: '' }};
let currentSignal = null;

function shorten(text, max) {{
  if (!text || text.length <= max) return text;
  return text.slice(0, max - 1) + '…';
}}

function escHtml(s) {{
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}

function matchesFilters(s) {{
  if (activeFilters.type !== 'all' && s.feed_type !== activeFilters.type) return false;
  if (activeFilters.tag !== 'all' && !s.tags.includes(activeFilters.tag)) return false;
  if (activeFilters.week !== 'all' && s.week_label !== activeFilters.week) return false;
  if (activeFilters.search) {{
    const q = activeFilters.search.toLowerCase();
    if (!(s.title + s.summary + s.company + s.topic).toLowerCase().includes(q)) return false;
  }}
  return true;
}}

function buildTagsHtml(tags) {{
  return tags.map(t =>
    `<span class="tag" style="${{tagStyle(t)}}">${{t.replace(/_/g,' ')}}</span>`
  ).join('');
}}

function buildCard(s, i) {{
  const tagsHtml = buildTagsHtml(s.tags);
  const delay = Math.min(i * 25, 400);
  return `
<div class="card" style="animation-delay:${{delay}}ms" onclick="openModal(${{i}})">
  <div class="card-header">
    <span class="card-company ${{s.feed_type}}">${{escHtml(s.company)}}</span>
    <div class="card-right">
      ${{s.topic ? `<span class="card-topic">${{escHtml(s.topic)}}</span>` : ''}}
      <span class="card-cw">${{s.cw}}</span>
    </div>
  </div>
  <div class="card-body">
    <div class="card-title">${{escHtml(s.title)}}</div>
    <div class="card-summary">${{escHtml(shorten(s.summary, 200))}}</div>
    ${{tagsHtml ? `<div class="card-tags">${{tagsHtml}}</div>` : ''}}
  </div>
  <div class="card-footer">
    <a class="read-btn" href="${{escHtml(s.url)}}" target="_blank" rel="noopener" onclick="event.stopPropagation()">Read the source</a>
    <span class="expand-hint">click to expand</span>
  </div>
</div>`;
}}

// Store filtered signals for modal navigation
let filteredSignals = [];
let filteredIndices = [];

function renderGrid() {{
  const grid = document.getElementById('grid');
  filteredSignals = SIGNALS.filter(matchesFilters);
  filteredIndices = filteredSignals.map((s, i) => i);

  document.getElementById('stat-total').textContent = filteredSignals.length;
  document.getElementById('stat-comp').textContent = filteredSignals.filter(s => s.feed_type === 'competitor').length;
  document.getElementById('stat-client').textContent = filteredSignals.filter(s => s.feed_type === 'client').length;

  if (filteredSignals.length === 0) {{
    grid.innerHTML = `<div class="empty"><h3>No signals found</h3><p>Try adjusting your filters.</p></div>`;
    return;
  }}

  const competitors = filteredSignals.filter(s => s.feed_type === 'competitor');
  const clients = filteredSignals.filter(s => s.feed_type === 'client');

  let html = '';
  let idx = 0;

  if (competitors.length > 0) {{
    if (clients.length > 0) {{
      html += `<div class="section-divider">
        <span class="section-divider-label" style="color:var(--competitor)">Competitor Intelligence</span>
        <div class="section-divider-line"></div></div>`;
    }}
    competitors.forEach(s => {{ html += buildCard(s, idx++); }});
  }}

  if (clients.length > 0) {{
    html += `<div class="section-divider">
      <span class="section-divider-label" style="color:var(--client)">Client Signals</span>
      <div class="section-divider-line"></div></div>`;
    clients.forEach(s => {{ html += buildCard(s, idx++); }});
  }}

  grid.innerHTML = html;
}}

function openModal(gridIdx) {{
  const s = filteredSignals[gridIdx];
  if (!s) return;
  currentSignal = s;

  document.getElementById('modal-company').textContent = s.company + (s.topic ? ` — ${{s.topic}}` : '');
  document.getElementById('modal-company').className = `modal-company ${{s.feed_type}}`;
  document.getElementById('modal-title').textContent = s.title;
  document.getElementById('modal-summary').textContent = s.summary || 'No summary available.';
  document.getElementById('modal-link').href = s.url;
  document.getElementById('modal-tags').innerHTML = buildTagsHtml(s.tags);

  document.getElementById('modal-meta').innerHTML = `
    <span class="modal-meta-item">${{s.cw}}</span>
    <span class="modal-meta-item">${{s.feed_type === 'competitor' ? 'Competitor' : 'Client Signal'}}</span>
    ${{s.tags.map(t => `<span class="modal-meta-item" style="${{tagStyle(t)}}">${{t.replace(/_/g,' ')}}</span>`).join('')}}
  `;

  document.getElementById('modal-overlay').classList.add('open');
  document.body.style.overflow = 'hidden';
}}

function closeModal() {{
  document.getElementById('modal-overlay').classList.remove('open');
  document.body.style.overflow = '';
  currentSignal = null;
}}

document.getElementById('modal-close').addEventListener('click', closeModal);
document.getElementById('modal-close2').addEventListener('click', closeModal);
document.getElementById('modal-overlay').addEventListener('click', e => {{
  if (e.target === document.getElementById('modal-overlay')) closeModal();
}});

// Filter pills
document.querySelectorAll('.pill[data-filter]').forEach(pill => {{
  pill.addEventListener('click', () => {{
    const ft = pill.dataset.filter;
    document.querySelectorAll(`.pill[data-filter="${{ft}}"]`).forEach(p => p.classList.remove('active'));
    pill.classList.add('active');
    activeFilters[ft] = pill.dataset.value;
    renderGrid();
  }});
}});

// Search
document.getElementById('search').addEventListener('input', e => {{
  activeFilters.search = e.target.value.trim();
  renderGrid();
}});

// Keyboard shortcuts
document.addEventListener('keydown', e => {{
  if (e.key === 'Escape') {{
    if (document.getElementById('modal-overlay').classList.contains('open')) {{
      closeModal();
    }} else {{
      // Reset all filters
      activeFilters = {{ type: 'all', tag: 'all', week: 'all', search: '' }};
      document.getElementById('search').value = '';
      document.querySelectorAll('.pill').forEach(p => p.classList.remove('active'));
      document.querySelectorAll('.pill[data-value="all"]').forEach(p => p.classList.add('active'));
      renderGrid();
    }}
  }}
  if (e.key === '/' && document.activeElement !== document.getElementById('search')) {{
    e.preventDefault();
    document.getElementById('search').focus();
  }}
}});

// Initial render
renderGrid();
</script>
{photo_html_footer}
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
