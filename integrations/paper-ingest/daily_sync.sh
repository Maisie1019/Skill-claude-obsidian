#!/usr/bin/env bash
# Daily vault sync for the quant-paper report pipeline. Runs inside WSL.
#
#   daily_paper_report.py  ->  vault/inbox/*.md      (plain writes, Windows side)
#   this script            ->  .raw/captured + wiki  (transactions, WSL side)
#
# Local integration layer: additive to the upstream tree, so `git pull upstream`
# never conflicts.
#
# Stages: capture (immutable payloads) -> ingest (source pages + source ledger
# + index/hot/log) -> lint. Claims are never written here; asserting what a
# paper found requires reading it, which is a human step.
#
# Usage:
#   daily_sync.sh                 # dry-run: show the plan, change nothing
#   daily_sync.sh --apply         # execute both transactions
#
# Both transactions review their own plan hash and re-submit it verbatim. That
# gate is mechanical here on purpose: this pipeline only ever creates source
# pages and source records, never claims and never a `verified` status.

set -euo pipefail

PRODUCT_ROOT="${PRODUCT_ROOT:-/mnt/e/Skills/obsidian-paper}"
VAULT="${VAULT:-/mnt/e/Skills/obsidian-vault}"
CLI="$PRODUCT_ROOT/scripts/claude-obsidian.py"
BUILDER="$PRODUCT_ROOT/integrations/paper-ingest/build_ingest_bundle.py"

APPLY=0
REFRESH=()
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    # Rewrites existing source pages whose content changed, discarding any human
    # annotation on them. Never passed by the nightly run; explicit use only.
    --refresh-pages) REFRESH=(--refresh-pages) ;;
    *) echo "未知参数：$arg" >&2; exit 2 ;;
  esac
done

TODAY="$(date -u +%Y-%m-%d)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
GENERATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
BUNDLE="$(mktemp -t paper-ingest-XXXXXX.json)"
trap 'rm -f "$BUNDLE"' EXIT

cd "$PRODUCT_ROOT"

log() { printf '\n== %s ==\n' "$1"; }

# Read one top-level string field out of a CLI JSON response.
json_field() { python3 -c 'import json,sys; print(json.load(sys.stdin).get(sys.argv[1]) or "")' "$1"; }

# ---------------------------------------------------------------- capture ----
log "capture (dry-run)"
CAPTURE_ID="paper-capture-$STAMP"
capture_plan="$(python3 "$CLI" capture apply --vault "$VAULT" \
  --generated-at "$GENERATED_AT" --operation-id "$CAPTURE_ID" 2>/dev/null)"
capture_writes="$(printf '%s' "$capture_plan" \
  | python3 -c 'import json,sys; p=json.load(sys.stdin); print(len((p.get("operation") or {}).get("writes") or []))')"
echo "待固化载荷：$capture_writes"

if (( APPLY )) && (( capture_writes > 0 )); then
  # The hash is only emitted when there is something to approve; a `noop`
  # plan carries none, which is why the write count is checked first.
  capture_hash="$(printf '%s' "$capture_plan" | json_field approved_plan_sha256)"
  [[ -n "$capture_hash" ]] || { echo "capture 计划未返回审批哈希。" >&2; exit 1; }
  log "capture (apply)"
  python3 "$CLI" capture apply --vault "$VAULT" \
    --generated-at "$GENERATED_AT" --operation-id "$CAPTURE_ID" \
    --approved-plan-sha256 "$capture_hash" --apply >/dev/null
  echo "已固化 $capture_writes 份载荷。"
fi

# ----------------------------------------------------------------- ingest ----
log "build ingest bundle"
set +e
python3 "$BUILDER" --vault "$VAULT" --out "$BUNDLE" \
  --operation-id "ingest-papers-$STAMP" --today "$TODAY" "${REFRESH[@]+"${REFRESH[@]}"}"
build_rc=$?
set -e

# 3 = nothing new to ingest. Not a failure; the day simply added no sources.
if (( build_rc == 3 )); then
  echo "无新增来源，结束。"
  exit 0
fi
(( build_rc == 0 )) || { echo "构建 bundle 失败（$build_rc）。" >&2; exit "$build_rc"; }

log "transaction inspect"
plan="$(python3 "$CLI" transaction inspect "$BUNDLE" --vault "$VAULT" 2>/dev/null)"
printf '%s' "$plan" | python3 -c '
import json,sys
d=json.load(sys.stdin)
print("valid:", d.get("valid"))
for p in d.get("changed_paths") or []: print("  ", p)
'

if ! (( APPLY )); then
  echo
  echo "以上为 dry-run。确认无误后加 --apply 执行。"
  exit 0
fi

approval="$(printf '%s' "$plan" | json_field approval_sha256)"
[[ -n "$approval" ]] || { echo "计划无效，未取得审批哈希。" >&2; exit 1; }

log "transaction apply"
python3 "$CLI" transaction apply "$BUNDLE" --vault "$VAULT" \
  --approved-plan-sha256 "$approval" 2>/dev/null | json_field status

# ------------------------------------------------------------------- lint ----
log "lint"
python3 "$CLI" lint --vault "$VAULT" 2>/dev/null \
  | python3 -c 'import json,sys; s=json.load(sys.stdin)["summary"]; print("issues:", s["issues_found"], "| pages:", s["pages_scanned"], "| links:", s["links_scanned"]); sys.exit(1 if s["issues_found"] else 0)'
