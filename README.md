# TLCA — Thought Leadership Collection Agent

> Automated competitor & client intelligence for GBS / Finance Transformation consulting.
> Weekly newsletter + interactive dashboard — fully automated via cron.

**Built by [Moritz Richter](https://www.linkedin.com/in/moritz-richter) · Business Consulting Finance**

---

## What it does

TLCA monitors public sources for strategic signals relevant to **Global Business Services (GBS)**, **Global Capability Centers (GCC)**, and **Agentic AI** — and delivers a curated weekly intelligence brief automatically.

```
Google Alerts (RSS feeds)
        ↓
intel_ingest_stdlib.py     →  SQLite database
        ↓
summarize_new_links.py     →  Claude Haiku (relevance scoring + summarization)
        ↓
weekly_newsletter_output.py →  HTML newsletter (score ≥ 3 only)
generate_dashboard.py       →  Intelligence Explorer (interactive HTML)
send_newsletter.py          →  Gmail → inbox
```

**Every Monday morning, automatically:**
- Ingests 50+ RSS feeds across competitors and client companies
- Scores each article 1–3 for strategic relevance using Claude
- Renders a newsletter with only the highest-signal articles
- Builds an interactive dashboard for deeper exploration
- Sends the newsletter by email
- Archives output by calendar week

---

## Intelligence Explorer

The dashboard (`intelligence_explorer.html`) is a standalone dark-theme HTML file — no server needed, just open in a browser.

**Features:**
- Card grid with competitor + client signal separation
- Competitor cards grouped by cluster: **MBB · Big4 · Accenture**
- Filter by type, topic tag (GBS / GCC / Agentic AI / Operating Model), calendar week
- Full-text search across titles, summaries, companies
- Click-to-expand modal with full summary + source link
- Relevance badges: **★ HIGH · MED · LOW**
- Keyboard shortcuts: `/` search · `Esc` reset

---

## Relevance Scoring

Each article is scored by Claude before summarizing:

| Score | Label | Meaning | Newsletter |
|---|---|---|---|
| 3 | ★ HIGH | Direct strategic signal: new offering, GBS/AI publication, C-suite move, M&A | ✅ |
| 2 | MED | Indirect signal: market commentary, trend piece | Explorer only |
| 1 | LOW | Weak signal: generic news | Explorer only |
| 0 | SKIP | Job post, stock tracker, ETF filing, economic indicator | Discarded |

---

## Setup

### 1. Clone and install
```bash
git clone https://github.com/YOUR_USERNAME/tlca.git
cd tlca
pip3 install -r requirements.txt
chmod +x run_weekly.sh
```

### 2. Configure API keys
```bash
export ANTHROPIC_API_KEY="sk-ant-..."          # https://console.anthropic.com
export GMAIL_USER="your@gmail.com"
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"  # https://myaccount.google.com/apppasswords
export INTEL_RECIPIENTS="recipient@email.com"
```

Add to `~/.zshrc` or `~/.bashrc` for persistence.

### 3. Configure feeds
```bash
cp sources.example.json sources.json
```

Edit `sources.json`:
1. Go to [google.com/alerts](https://www.google.com/alerts)
2. Create alerts with **Deliver to: RSS feed**
3. Copy feed URLs into `sources.json`
4. Add company names to `competitor_sources` or `client_sources`

### 4. Run
```bash
bash run_weekly.sh
```

Output in `output/CW_YYYY_WW/`:
- `newsletter_full.html` — full email (open in browser to preview)
- `newsletter_block.html` — article blocks only
- `newsletter_block.txt` — plain text
- `client_signals.html` — client signals only
- `intelligence_explorer.html` — interactive dashboard

### 5. Schedule (every Monday 07:30)
```bash
(crontab -l 2>/dev/null; echo "30 5 * * 1 cd /path/to/tlca && bash run_weekly.sh >> logs/weekly.log 2>&1") | crontab -
```
Adjust UTC offset for your timezone.

---

## Customization

### Add a company to track
In `sources.json`:
```json
{
  "source": "CompanyName_Finance",
  "url": "https://www.google.com/alerts/feeds/YOUR_ID/FEED_ID"
}
```
Add `"CompanyName"` to `competitor_sources` or `client_sources`.

### Add blocked domains (noise filter)
```json
"blocked_domains": ["gurufocus.com", "marketbeat.com"]
```

### Change newsletter score threshold
```bash
export INTEL_MIN_SCORE=2   # include MED signals (default: 3)
```

### Add your photo to the dashboard footer
```bash
cp your-photo.jpg photo.jpg
export INTEL_PHOTO_PATH="photo.jpg"
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **Required.** Claude API key |
| `GMAIL_USER` | `your@gmail.com` | Gmail sender |
| `GMAIL_APP_PASSWORD` | — | Gmail App Password |
| `INTEL_RECIPIENTS` | `recipient@email.com` | Comma-separated recipients |
| `INTEL_DB_PATH` | `intel.db` | SQLite database |
| `INTEL_WINDOW_DAYS` | `7` | Newsletter lookback window |
| `INTEL_MIN_SCORE` | `3` | Minimum relevance score for newsletter |
| `INTEL_MAX_SUMMARIZE` | `30` | Max articles to summarize per run |
| `INTEL_DASHBOARD_WEEKS` | `4` | Explorer lookback in weeks |
| `CLAUDE_MODEL` | `claude-haiku-4-5-20251001` | Claude model |
| `INTEL_PHOTO_PATH` | `photo.jpg` | Footer photo path |

---

## Stack

- **Python 3.10+** — no heavy ML dependencies
- **SQLite** — lightweight local database
- **Claude Haiku** ([Anthropic](https://anthropic.com)) — fast, cheap summarization + scoring
- **Gmail SMTP** — newsletter delivery
- **Google Alerts** — RSS feed source (free)
- **Vanilla HTML/JS** — dashboard, no framework needed

---

## Suggested Alert Queries

**Competitor monitoring:**
```
site:mckinsey.com ("operating model" OR "global business services" OR "agentic ai")
site:deloitte.com ("finance transformation" OR "shared services" OR "GBS")
```

**Client monitoring:**
```
"CompanyName" "finance transformation" OR "CFO" OR "operating model"
"CompanyName" "shared services" OR "GBS" OR "global business services"
```

---

## License

MIT — free to use, modify, and distribute.

---

*Built as a personal project to automate competitive intelligence for GBS and finance transformation consulting. Contributions welcome.*
