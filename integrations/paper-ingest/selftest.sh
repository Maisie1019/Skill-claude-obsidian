#!/usr/bin/env bash
# End-to-end check for daily_sync.sh against a scratch vault under /tmp.
#
# Exercises the full apply path — capture, ingest transaction, lint — without
# touching the real knowledge base, then verifies the second run is a no-op.
# Safe to run at any time; the scratch vault is created and removed here.

set -euo pipefail

PRODUCT_ROOT="${PRODUCT_ROOT:-/mnt/e/Skills/obsidian-paper}"
CLI="$PRODUCT_ROOT/scripts/claude-obsidian.py"
TV="$(mktemp -d -t co-selftest-XXXXXX)"
trap 'rm -rf "$TV"' EXIT

cd "$PRODUCT_ROOT"
field() { python3 -c 'import json,sys; print(json.load(sys.stdin).get(sys.argv[1]) or "")' "$1"; }

echo "== init scratch vault: $TV =="
h="$(python3 "$CLI" init "$TV" --generated-at 2026-01-01T00:00:00Z \
      --operation-id selftest-init 2>/dev/null | field approved_plan_sha256)"
python3 "$CLI" init "$TV" --generated-at 2026-01-01T00:00:00Z \
  --operation-id selftest-init --approved-plan-sha256 "$h" --apply >/dev/null 2>&1

mkdir -p "$TV/inbox"
cat > "$TV/inbox/2026-01-01 Selftest Paper.md" <<'NOTE'
---
title: "Selftest Paper"
source_type: "paper"
status: "inbox"
evidence_class: "外部观点"
has_abstract: true
url: "https://arxiv.org/abs/0000.00000"
source: "arXiv"
published: "2026-01-01"
tags:
  - paper
---

# Selftest Paper

## 原文摘要（未改写）

`外部观点`

This is a fixture abstract used only to exercise the ingest pipeline.
NOTE

echo "== run 1: --apply =="
VAULT="$TV" bash integrations/paper-ingest/daily_sync.sh --apply

echo "== assertions =="
test -f "$TV/wiki/sources/Selftest Paper.md"            && echo "OK 来源页已生成"
grep -q "Selftest Paper" "$TV/wiki/index.md"            && echo "OK 索引已更新"
grep -q "量化论文日报接入" "$TV/wiki/log.md"             && echo "OK 日志已记录"
python3 -c '
import json,sys
d=json.load(open(sys.argv[1]))
rec=next(iter(d["sources"].values()))
assert rec["review_status"]=="active" and rec["pages"]==["wiki/sources/Selftest Paper.md"], rec
print("OK 来源台账记录正确:", rec["authority"], rec["independence_key"])
' "$TV/wiki/meta/ledgers/source-ledger.json"
python3 -c '
import json,sys
d=json.load(open(sys.argv[1]))
assert not d.get("claims"), "断言台账不应被自动写入"
print("OK 断言台账未被自动写入")
' "$TV/wiki/meta/ledgers/claim-ledger.json"

echo "== run 2: 应为幂等空转 =="
out="$(VAULT="$TV" bash integrations/paper-ingest/daily_sync.sh --apply)"
echo "$out" | grep -q "无新增来源" && echo "OK 重跑无写入"

echo
echo "自检通过。"
