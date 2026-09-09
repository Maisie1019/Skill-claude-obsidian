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

# `capture` walks the whole inbox on every run, not just the notes it has yet to
# fix, so its 100-item default budget is measured against the inbox's total size
# rather than the day's additions. Once the inbox passed 100 notes the nightly
# run began refusing every night with COUNT_BUDGET_EXCEEDED. Raise the ceiling
# to something the inbox is unlikely to reach on its own; a run that genuinely
# needs more than this is not a normal night and should stop for a look.
MAX_ITEMS="${MAX_ITEMS:-500}"
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

# Chunks and the BM25 index are derived caches under .vault-meta/, not knowledge,
# so this needs no transaction. Prefixing is incremental — unchanged pages are
# skipped by hash — which makes a nightly rebuild cheap enough to be automatic.
#
# Runs even on a night that ingests nothing, because the pages a human writes by
# hand (concept and method pages) change the vault without any paper arriving,
# and those are precisely the pages worth finding. A stale index is worse than
# no index: it still answers, just about yesterday's vault.
reindex() {
  log "reindex"
  python3 "$PRODUCT_ROOT/scripts/contextual-prefix.py" --vault "$VAULT" --all --no-llm \
    2>/dev/null | tail -1
  python3 "$PRODUCT_ROOT/scripts/bm25-index.py" --vault "$VAULT" build 2>/dev/null | tail -1
}

# Read one top-level string field out of a CLI JSON response.
json_field() { python3 -c 'import json,sys; print(json.load(sys.stdin).get(sys.argv[1]) or "")' "$1"; }

# ---------------------------------------------------------------- capture ----
log "capture (dry-run)"
CAPTURE_ID="paper-capture-$STAMP"
capture_plan="$(python3 "$CLI" capture apply --vault "$VAULT" \
  --generated-at "$GENERATED_AT" --operation-id "$CAPTURE_ID" \
  --max-items "$MAX_ITEMS" 2>/dev/null)"

# `capture` reports its refusals on stderr and still exits 0, so neither `set -e`
# nor the exit status catches a budget or validation failure. An unparseable plan
# is the only signal, and it has to be treated as fatal: continuing would ingest
# source pages whose payloads were never written.
capture_writes="$(printf '%s' "$capture_plan" | python3 -c '
import json, sys
try:
    plan = json.loads(sys.stdin.read())
except ValueError:
    sys.exit(1)
print(len((plan.get("operation") or {}).get("writes") or []))
')" || {
  echo "capture 未返回可解析的计划。重跑并去掉 2>/dev/null 查看原因：" >&2
  echo "  python3 $CLI capture apply --vault $VAULT \\" >&2
  echo "    --generated-at $GENERATED_AT --operation-id $CAPTURE_ID --max-items $MAX_ITEMS" >&2
  exit 1
}
echo "待固化载荷：$capture_writes"

if (( APPLY )) && (( capture_writes > 0 )); then
  # The hash is only emitted when there is something to approve; a `noop`
  # plan carries none, which is why the write count is checked first.
  capture_hash="$(printf '%s' "$capture_plan" | json_field approved_plan_sha256)"
  [[ -n "$capture_hash" ]] || { echo "capture 计划未返回审批哈希。" >&2; exit 1; }
  log "capture (apply)"
  python3 "$CLI" capture apply --vault "$VAULT" \
    --generated-at "$GENERATED_AT" --operation-id "$CAPTURE_ID" \
    --max-items "$MAX_ITEMS" \
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
  echo "无新增来源。"
  reindex
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

# ---------------------------------------------------------------- reindex ----
# Chunks and the BM25 index are derived caches under .vault-meta/, not knowledge,
# so this needs no transaction. Prefixing is incremental — unchanged pages are
# skipped by hash — which makes a nightly rebuild cheap enough to be automatic.
# Left out, the index silently describes yesterday's vault, which is worse than
# having no index at all because it still returns confident answers.
reindex

# ------------------------------------------------------------------- lint ----
log "lint"
python3 "$CLI" lint --vault "$VAULT" 2>/dev/null \
  | python3 -c 'import json,sys; s=json.load(sys.stdin)["summary"]; print("issues:", s["issues_found"], "| pages:", s["pages_scanned"], "| links:", s["links_scanned"]); sys.exit(1 if s["issues_found"] else 0)'
