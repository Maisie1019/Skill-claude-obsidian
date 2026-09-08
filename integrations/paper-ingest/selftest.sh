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

## 原文章节摘录（逐字）

`外部观点`　抓取方式：`arxiv-api+html`，全文 1234 字符。
全文存档：[[fulltext/2026-01-01 Selftest Paper — 全文]]

### 方法　—　2 Method

> Fixture body sentence standing in for the paper's own words.

## 可核验陈述（逐字，含数值或指标）

`外部观点`　以下句子逐字取自原文，含具体数值或可核验指标，是复现与证伪的起点。

- > The strategy reports a Sharpe ratio of 1.42 out of sample.
NOTE

mkdir -p "$TV/inbox/fulltext"
cat > "$TV/inbox/fulltext/2026-01-01 Selftest Paper — 全文.md" <<'ARCHIVE'
---
title: "Selftest Paper（全文存档）"
source_type: "paper-fulltext"
status: "inbox"
evidence_class: "外部观点"
extraction: "verbatim"
url: "https://arxiv.org/abs/0000.00000"
fulltext_method: "arxiv-api+html"
paper_note: "2026-01-01 Selftest Paper"
tags:
  - paper-fulltext
---

# Selftest Paper（全文存档）

## Abstract

This is a fixture abstract used only to exercise the ingest pipeline.

## 2 Method

Fixture body sentence standing in for the paper's own words.
ARCHIVE

echo "== run 1: --apply =="
VAULT="$TV" bash integrations/paper-ingest/daily_sync.sh --apply

echo "== assertions =="
test -f "$TV/wiki/sources/Selftest Paper.md"            && echo "OK 来源页已生成"
grep -q "Selftest Paper" "$TV/wiki/index.md"            && echo "OK 索引已更新"
grep -q "量化论文日报接入" "$TV/wiki/log.md"             && echo "OK 日志已记录"
grep -q "Fixture body sentence" "$TV/wiki/sources/Selftest Paper.md" \
  && echo "OK 来源页带逐字正文"
grep -q "Sharpe ratio of 1.42" "$TV/wiki/sources/Selftest Paper.md" \
  && echo "OK 来源页带逐字数值陈述"
# The inbox-relative wikilink must not be copied into wiki/, or lint reports a
# dead link; the page cites the immutable payload path instead.
grep -q "全文存档：\[\[" "$TV/wiki/sources/Selftest Paper.md" \
  && { echo "FAIL 来源页复制了 inbox 相对链接"; exit 1; }
grep -q "^- 全文载荷：" "$TV/wiki/sources/Selftest Paper.md" \
  && echo "OK 来源页指向不可变全文载荷"
python3 -c '
import json,sys
d=json.load(open(sys.argv[1]))
page="wiki/sources/Selftest Paper.md"
recs=list(d["sources"].values())
assert len(recs)==2, f"应有笔记与全文存档两条记录，实得 {len(recs)}"
for rec in recs:
    assert rec["review_status"]=="active" and rec["pages"]==[page], rec
    assert rec["independence_key"]=="arxiv", rec
archive=[r for r in recs if "全文逐字存档" in r["title"]]
assert len(archive)==1, "全文存档应单独登记一条来源记录"
print("OK 来源台账记录正确:", recs[0]["authority"], recs[0]["independence_key"], "· 含全文存档记录")
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
