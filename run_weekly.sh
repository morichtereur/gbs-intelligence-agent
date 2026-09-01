#!/usr/bin/env bash
# run_weekly.sh — TLCA Weekly Pipeline
#
# SETUP:
#   chmod +x run_weekly.sh
#   pip3 install -r requirements.txt
#   export ANTHROPIC_API_KEY="sk-ant-..."
#   export GMAIL_USER="your@gmail.com"
#   export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
#   export INTEL_RECIPIENTS="recipient@email.com"
#
# CRON (every Monday 07:30 local time, adjust UTC offset):
#   30 5 * * 1 cd /path/to/tlca && bash run_weekly.sh >> logs/weekly.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "=================================================="
echo " TLCA — Weekly Intelligence Pipeline"
echo " $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "=================================================="

set_env_default() {
  local name="$1"; local value="$2"
  if [[ -z "${!name:-}" ]]; then
    export "$name"="$value"
    echo "[env] $name=$value (default)"
  else
    echo "[env] $name=${!name} (kept)"
  fi
}

run_step() {
  local label="$1"; local script="$2"
  echo ""; echo "==> $label"
  python3 "$script"
  echo "[OK] $label"
}

# ---------- env defaults ----------
set_env_default INTEL_DB_PATH            "intel.db"
set_env_default INTEL_SOURCES_PATH       "sources.json"
set_env_default INTEL_VERIFY_SSL         "1"
set_env_default ALLOW_INSECURE_SSL_FALLBACK "1"
set_env_default INTEL_HTTP_TIMEOUT       "25"
set_env_default INTEL_WINDOW_DAYS        "7"
set_env_default INTEL_MAX_SUMMARIZE      "30"
set_env_default INTEL_REQUIRE_TAG_MATCH  "1"
set_env_default INTEL_DEDUP_ON_CANONICAL "1"
set_env_default INTEL_ALLOWED_TAGS       "Finance_Strategy,GBS,GCC,Controlling_FPA,Agentic_AI,Client_Signal"
set_env_default INTEL_MIN_SCORE          "3"

set_env_default ENABLE_LLM               "1"
set_env_default CLAUDE_MODEL             "claude-haiku-4-5-20251001"
set_env_default CLAUDE_TIMEOUT_SECONDS   "45"

set_env_default INTEL_TEMPLATE_PATH      "templates/newsletter_template.html"
set_env_default INTEL_DASHBOARD_WEEKS    "4"

set_env_default INTEL_BTN_BG             "#27568C"
set_env_default INTEL_BTN_TXT            "#FFFFFF"
set_env_default INTEL_BTN_LABEL          "Read the source"
set_env_default INTEL_SUBJECT_PREFIX     "Weekly Competitor Intelligence Brief - GBS | GCC | Agentic AI"

set_env_default GMAIL_USER               "your@gmail.com"
set_env_default INTEL_RECIPIENTS         "recipient@email.com"

# Guard
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "[ERROR] ANTHROPIC_API_KEY is not set. Export it and retry."
  exit 1
fi

# ---------- pipeline ----------
# INTEL_OUT_ROOT lets a second instance (e.g. a team configuration) keep
# its database and editions outside the code folder.
set_env_default INTEL_OUT_ROOT           "output"
mkdir -p "$INTEL_OUT_ROOT" logs

if [[ ! -f "$INTEL_SOURCES_PATH" ]]; then
  echo "[ERROR] Sources file not found: $INTEL_SOURCES_PATH"
  echo "        Copy sources.example.json to sources.json and configure it."
  exit 1
fi

if [[ ! -f "$INTEL_TEMPLATE_PATH" ]]; then
  echo "[ERROR] Newsletter template not found: $INTEL_TEMPLATE_PATH"
  exit 1
fi

EDITION=$(python3 edition_counter.py --peek)
export INTEL_EDITION="$EDITION"
echo "[info] Edition: $EDITION"

CW=$(date +%V); YEAR=$(date +%Y)
export INTEL_OUT_DIR="${INTEL_OUT_ROOT}/CW_${YEAR}_${CW}"

run_step "1/6 Ingest feeds"         "intel_ingest_stdlib.py"
run_step "2/6 Summarize new links"  "summarize_new_links.py"
run_step "3/6 Write newsletter"     "weekly_newsletter_output.py"
run_step "4/6 Build explorer"       "generate_dashboard.py"
run_step "5/6 Build archive"        "generate_archive.py"
run_step "6/6 Send newsletter"      "send_newsletter.py"

python3 edition_counter.py --commit "$EDITION"
echo "[OK] Edition $EDITION committed"

echo ""
echo "=================================================="
echo " Done. $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo " Output → $INTEL_OUT_DIR"
echo "=================================================="
