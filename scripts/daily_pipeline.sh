#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${PATH:-}" ]]; then
  PATH="${PATH}:/Users/admin/.local/bin:/Users/admin/.bun/bin:/usr/bin:/bin:/usr/sbin:/sbin"
else
  PATH="/Users/admin/.local/bin:/Users/admin/.bun/bin:/usr/bin:/bin:/usr/sbin:/sbin"
fi
export PATH

TZ_REGION="Asia/Singapore"
LOOKBACK_DAYS=2
LOOKBACK_SET=0
START_DATE=""
END_DATE=""
SKIP_SUMMARIES=0
SKIP_DEPLOY=0
FORCE_DEPLOY=0
DRY_RUN=0
DATE_WINDOW_MODE="manual"
LATEST_SITTING_ISO=""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_DIR="${REPO_ROOT}/python"
ASTRO_DIR="${REPO_ROOT}/astro"
DB_PATH="${PARLIAMENT_DB_PATH:-${REPO_ROOT}/data/parliament.db}"

LOCK_BASE_DIR="${REPO_ROOT}/.locks"
LOCK_DIR="${LOCK_BASE_DIR}/daily_pipeline.lock"

LOG_DIR="${REPO_ROOT}/logs/pipeline"
RUN_TS="$(TZ="${TZ_REGION}" date '+%Y%m%d-%H%M%S')"
LOG_FILE="${LOG_DIR}/run-${RUN_TS}.log"

START_EPOCH="$(date +%s)"
DEPLOY_DECISION="not-evaluated"

usage() {
  cat <<'EOF'
Usage: scripts/daily_pipeline.sh [options]

Options:
  --start-date DD-MM-YYYY  Optional start date override
  --end-date DD-MM-YYYY    Optional end date override (defaults to start date)
  --lookback-days N        Recent window override: today-N through today
  --skip-summaries         Skip sitting summaries
  --skip-deploy            Skip Astro build/deploy even when data changed
  --force-deploy           Force Astro build/deploy regardless of data digest
  --dry-run                Print commands without executing them
  -h, --help               Show this help text
EOF
}

timestamp() {
  TZ="${TZ_REGION}" date '+%Y-%m-%d %H:%M:%S %Z'
}

log() {
  printf '[%s] %s\n' "$(timestamp)" "$*"
}

fail() {
  log "ERROR: $*"
  exit 1
}

cleanup() {
  local exit_code=$?
  local end_epoch elapsed
  end_epoch="$(date +%s)"
  elapsed=$((end_epoch - START_EPOCH))

  if [[ -d "${LOCK_DIR}" ]]; then
    rm -rf "${LOCK_DIR}"
  fi

  if [[ "${exit_code}" -eq 0 ]]; then
    log "Run completed successfully."
  else
    log "Run failed (exit code ${exit_code})."
  fi

  log "Deploy decision: ${DEPLOY_DECISION}"
  log "Elapsed seconds: ${elapsed}"
}

require_cmd() {
  local cmd="$1"
  command -v "${cmd}" >/dev/null 2>&1 || fail "Missing required command: ${cmd}"
}

format_cmd() {
  local out="" arg
  for arg in "$@"; do
    printf -v out '%s%q ' "${out}" "${arg}"
  done
  printf '%s' "${out% }"
}

run_in_dir() {
  local dir="$1"
  shift
  log "CMD (${dir}): $(format_cmd "$@")"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    return 0
  fi
  (
    cd "${dir}"
    "$@"
  )
}

to_iso_date() {
  local input="$1"
  TZ="${TZ_REGION}" date -j -f "%d-%m-%Y" "${input}" "+%Y-%m-%d" 2>/dev/null
}

get_latest_sitting_iso() {
  local db_path="$1"
  local latest=""

  if [[ -f "${db_path}" ]]; then
    latest="$(sqlite3 -readonly "${db_path}" "SELECT MAX(date) FROM sittings;" 2>/dev/null || true)"
  fi

  latest="${latest//$'\r'/}"
  printf '%s' "${latest}"
}

compute_digest() {
  local db_path="$1"
  local iso_start="$2"
  local iso_end="$3"

  if [[ ! -f "${db_path}" ]]; then
    printf 'MISSING'
    return 0
  fi

  sqlite3 -readonly "${db_path}" <<SQL | shasum -a 256 | awk '{print $1}'
.mode list
.separator |
SELECT 'sittings', s.id, s.date,
       COALESCE(s.sitting_no, ''), COALESCE(s.parliament, ''), COALESCE(s.session_no, ''),
       COALESCE(s.volume_no, ''), COALESCE(s.format, ''), COALESCE(s.url, '')
FROM sittings s
WHERE s.date >= '${iso_start}' AND s.date <= '${iso_end}'
ORDER BY s.date, s.id;

SELECT 'sections', sec.id, sec.sitting_id,
       COALESCE(sec.ministry_id, ''), COALESCE(sec.bill_id, ''), COALESCE(sec.category, ''),
       COALESCE(sec.section_type, ''), COALESCE(sec.section_title, ''), COALESCE(sec.content_html, ''),
       COALESCE(sec.content_plain, ''), COALESCE(sec.section_order, ''), COALESCE(sec.source_url, ''),
       COALESCE(sec.summary, '')
FROM sections sec
JOIN sittings s ON s.id = sec.sitting_id
WHERE s.date >= '${iso_start}' AND s.date <= '${iso_end}'
ORDER BY s.date, sec.section_order, sec.id;

SELECT 'section_speakers', ss.section_id, ss.member_id,
       COALESCE(ss.constituency, ''), COALESCE(ss.designation, '')
FROM section_speakers ss
WHERE ss.section_id IN (
  SELECT sec.id
  FROM sections sec
  JOIN sittings s ON s.id = sec.sitting_id
  WHERE s.date >= '${iso_start}' AND s.date <= '${iso_end}'
)
ORDER BY ss.section_id, ss.member_id;

SELECT 'sitting_attendance', sa.sitting_id, sa.member_id, sa.present,
       COALESCE(sa.constituency, ''), COALESCE(sa.designation, '')
FROM sitting_attendance sa
JOIN sittings s ON s.id = sa.sitting_id
WHERE s.date >= '${iso_start}' AND s.date <= '${iso_end}'
ORDER BY s.date, sa.member_id;

SELECT 'bills', b.id, b.title,
       COALESCE(b.ministry_id, ''), COALESCE(b.first_reading_date, ''),
       COALESCE(b.first_reading_sitting_id, ''), COALESCE(b.summary, '')
FROM bills b
WHERE b.id IN (
  SELECT DISTINCT sec.bill_id
  FROM sections sec
  JOIN sittings s ON s.id = sec.sitting_id
  WHERE s.date >= '${iso_start}' AND s.date <= '${iso_end}' AND sec.bill_id IS NOT NULL
)
ORDER BY b.id;
SQL
}

git_is_deploy_safe() {
  local branch filtered_status
  branch="$(git -C "${REPO_ROOT}" rev-parse --abbrev-ref HEAD)"
  if [[ "${branch}" != "main" ]]; then
    log "Deploy blocked: git branch is '${branch}', expected 'main'."
    return 1
  fi

  filtered_status="$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=no | grep -vE '^[ MADRCU?!]{2} \.DS_Store$' || true)"
  if [[ -n "${filtered_status}" ]]; then
    log "Deploy blocked: tracked git changes present."
    log "${filtered_status}"
    return 1
  fi

  return 0
}

for arg in "$@"; do
  if [[ "${arg}" == "-h" || "${arg}" == "--help" ]]; then
    usage
    exit 0
  fi
done

mkdir -p "${LOG_DIR}"
printf 'Logging to %s\n' "${LOG_FILE}"
exec >> "${LOG_FILE}" 2>&1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --start-date)
      [[ $# -ge 2 ]] || fail "Missing value for --start-date"
      START_DATE="$2"
      shift 2
      ;;
    --end-date)
      [[ $# -ge 2 ]] || fail "Missing value for --end-date"
      END_DATE="$2"
      shift 2
      ;;
    --lookback-days)
      [[ $# -ge 2 ]] || fail "Missing value for --lookback-days"
      LOOKBACK_DAYS="$2"
      LOOKBACK_SET=1
      shift 2
      ;;
    --skip-summaries)
      SKIP_SUMMARIES=1
      shift
      ;;
    --skip-deploy)
      SKIP_DEPLOY=1
      shift
      ;;
    --force-deploy)
      FORCE_DEPLOY=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown argument: $1"
      ;;
  esac
done

if ! [[ "${LOOKBACK_DAYS}" =~ ^[0-9]+$ ]]; then
  fail "--lookback-days must be a non-negative integer"
fi

if [[ -n "${END_DATE}" && -z "${START_DATE}" ]]; then
  fail "--end-date requires --start-date"
fi

if [[ -n "${START_DATE}" && -z "${END_DATE}" ]]; then
  END_DATE="${START_DATE}"
fi

if [[ -z "${START_DATE}" ]]; then
  if [[ "${LOOKBACK_SET}" -eq 1 ]]; then
    DATE_WINDOW_MODE="lookback"
    END_DATE="$(TZ="${TZ_REGION}" date '+%d-%m-%Y')"
    START_DATE="$(TZ="${TZ_REGION}" date -v-"${LOOKBACK_DAYS}"d '+%d-%m-%Y')"
  else
    DATE_WINDOW_MODE="incremental"
    LATEST_SITTING_ISO="$(get_latest_sitting_iso "${DB_PATH}")"
    END_DATE="$(TZ="${TZ_REGION}" date '+%d-%m-%Y')"

    if [[ -n "${LATEST_SITTING_ISO}" ]]; then
      START_DATE="$(TZ="${TZ_REGION}" date -j -v+1d -f "%Y-%m-%d" "${LATEST_SITTING_ISO}" '+%d-%m-%Y' 2>/dev/null || true)"
      [[ -n "${START_DATE}" ]] || fail "Failed to parse latest sitting date from DB: ${LATEST_SITTING_ISO}"
    else
      DATE_WINDOW_MODE="lookback-fallback"
      START_DATE="$(TZ="${TZ_REGION}" date -v-"${LOOKBACK_DAYS}"d '+%d-%m-%Y')"
      log "No sittings found in DB; falling back to lookback window (today-${LOOKBACK_DAYS} to today)."
    fi
  fi
fi

ISO_START="$(to_iso_date "${START_DATE}" || true)"
[[ -n "${ISO_START}" ]] || fail "Invalid --start-date format (expected DD-MM-YYYY): ${START_DATE}"
ISO_END="$(to_iso_date "${END_DATE}" || true)"
[[ -n "${ISO_END}" ]] || fail "Invalid --end-date format (expected DD-MM-YYYY): ${END_DATE}"

if [[ "${ISO_START}" > "${ISO_END}" ]]; then
  if [[ "${DATE_WINDOW_MODE}" == "incremental" && "${LATEST_SITTING_ISO}" == "${ISO_END}" ]]; then
    log "No new sittings to ingest. Latest ingested date is ${LATEST_SITTING_ISO}."
    exit 0
  fi
  fail "Start date must be <= end date (${START_DATE} > ${END_DATE})"
fi

mkdir -p "${LOCK_BASE_DIR}"
if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  fail "Another daily_pipeline.sh run is already in progress (${LOCK_DIR})"
fi
echo "$$" > "${LOCK_DIR}/pid"

trap cleanup EXIT

require_cmd uv
require_cmd bun
require_cmd git
require_cmd sqlite3
require_cmd shasum

log "Starting daily pipeline."
log "Repo root: ${REPO_ROOT}"
log "Date range: ${START_DATE} to ${END_DATE} (ISO ${ISO_START} to ${ISO_END})"
log "Date window mode: ${DATE_WINDOW_MODE}"
if [[ -n "${LATEST_SITTING_ISO}" ]]; then
  log "Latest ingested sitting date in DB: ${LATEST_SITTING_ISO}"
fi
log "DB path: ${DB_PATH}"
log "Flags: skip_summaries=${SKIP_SUMMARIES}, skip_deploy=${SKIP_DEPLOY}, force_deploy=${FORCE_DEPLOY}, dry_run=${DRY_RUN}"

if [[ "${DRY_RUN}" -eq 1 ]]; then
  PRE_DIGEST="dry-run"
else
  PRE_DIGEST="$(compute_digest "${DB_PATH}" "${ISO_START}" "${ISO_END}")"
fi
log "Pre-run digest: ${PRE_DIGEST}"

run_in_dir "${PYTHON_DIR}" uv run batch_process_sqlite.py "${START_DATE}" "${END_DATE}"
run_in_dir "${PYTHON_DIR}" uv run cleanup_duplicates_sqlite.py "${START_DATE}" "${END_DATE}" --keep-newest

if [[ "${SKIP_SUMMARIES}" -eq 0 ]]; then
  run_in_dir "${PYTHON_DIR}" uv run generate_summaries_sqlite.py --sittings "${START_DATE}" "${END_DATE}" --only-blank
else
  log "Skipping sitting summaries (--skip-summaries)."
fi

POST_DIGEST="${PRE_DIGEST}"
if [[ "${DRY_RUN}" -eq 0 ]]; then
  POST_DIGEST="$(compute_digest "${DB_PATH}" "${ISO_START}" "${ISO_END}")"
fi
log "Post-run digest: ${POST_DIGEST}"

DATA_CHANGED=0
if [[ "${PRE_DIGEST}" != "${POST_DIGEST}" ]]; then
  DATA_CHANGED=1
fi
log "Data changed: ${DATA_CHANGED}"

if [[ "${SKIP_DEPLOY}" -eq 1 ]]; then
  DEPLOY_DECISION="skipped (--skip-deploy)"
  log "Skipping deploy by flag."
elif [[ "${DRY_RUN}" -eq 1 ]]; then
  DEPLOY_DECISION="dry-run (not executed)"
  log "Dry run enabled: build/deploy not executed."
elif [[ "${FORCE_DEPLOY}" -eq 1 ]]; then
  if ! git_is_deploy_safe; then
    fail "Force deploy requested but git safety check failed."
  fi
  run_in_dir "${ASTRO_DIR}" bun run build
  run_in_dir "${ASTRO_DIR}" bun run deploy
  DEPLOY_DECISION="forced deploy"
elif [[ "${DATA_CHANGED}" -eq 1 ]]; then
  if ! git_is_deploy_safe; then
    fail "Data changed but git safety check failed."
  fi
  run_in_dir "${ASTRO_DIR}" bun run build
  run_in_dir "${ASTRO_DIR}" bun run deploy
  DEPLOY_DECISION="deployed (data changed)"
else
  DEPLOY_DECISION="skipped (no data changes)"
  log "No semantic data change detected; skipping build/deploy."
fi
