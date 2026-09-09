#!/usr/bin/env python3
"""Search the vault's paper pages and hand back where to read the real text.

Thin caller-side wrapper over the product's own retrieval stack. It exists for
two reasons, both of which are properties of this vault rather than bugs in the
stack, so neither is fixed by editing upstream:

1. `wiki/index.md` and `wiki/hot.md` are bags of paper titles. Any query made of
   title words scores them highly — they took two of the top five slots on half
   the probe queries. They are navigation, not evidence, so they are dropped.

2. The index covers `wiki/` only, and a source page is a short summary. The
   paper itself — a median of 46k characters — lives in `.raw/captured/`. So a
   hit is a pointer, not an answer: this prints the payload path alongside each
   result and expects the caller to go read it.

That is the same two-level shape the extraction pass uses: cheap mechanical
selection over everything, careful reading over the survivors only.

    python find_papers.py "market making inventory risk" --top 8

Read-only. Runs natively on Windows; no transaction, no vault mutation.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

PRODUCT_ROOT = Path(__file__).resolve().parents[2]
RETRIEVE = PRODUCT_ROOT / "scripts" / "retrieve.py"

# Navigation and bookkeeping pages. They are legitimate wiki content and stay
# indexed — they are simply never the answer to a research question.
NAVIGATION = {"wiki/index.md", "wiki/hot.md", "wiki/log.md", "wiki/overview.md"}


def frontmatter(path: Path) -> Dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    match = re.match(r"---\n(.*?)\n---", text, re.S)
    if not match:
        return {}
    props: Dict[str, str] = {}
    for line in match.group(1).splitlines():
        if line.startswith((" ", "-")) or ":" not in line:
            continue
        key, _, value = line.partition(":")
        props[key.strip()] = value.strip().strip('"').strip("'")
    return props


def search(vault: Path, query: str, pool: int) -> List[dict]:
    """Ask the product's retriever for candidates, or explain why it cannot."""
    result = subprocess.run(
        [sys.executable, str(RETRIEVE), "--vault", str(vault), query,
         "--top", str(pool), "--no-rerank"],
        capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode == 10:
        raise SystemExit(
            "检索索引不存在。先建索引（WSL）：\n"
            "  python3 scripts/contextual-prefix.py --vault <vault> --all --no-llm\n"
            "  python3 scripts/bm25-index.py --vault <vault> build"
        )
    if result.returncode != 0:
        raise SystemExit(f"retrieve.py 失败（{result.returncode}）：{result.stderr[:400]}")
    return json.loads(result.stdout).get("candidates") or []


def collapse(candidates: Sequence[dict]) -> List[dict]:
    """One row per page, keeping its best-scoring chunk.

    A long paper contributes several chunks and would otherwise fill the list
    with itself.
    """
    best: Dict[str, dict] = {}
    for candidate in candidates:
        path = candidate.get("page_path") or ""
        if path in NAVIGATION:
            continue
        prior = best.get(path)
        if prior is None or candidate["bm25_score"] > prior["bm25_score"]:
            best[path] = candidate
    return sorted(best.values(), key=lambda c: -c["bm25_score"])


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("query")
    parser.add_argument("--vault", default=r"E:/Skills/obsidian-vault")
    parser.add_argument("--top", type=int, default=8, help="返回多少篇（缺省 8）")
    args = parser.parse_args(argv)

    vault = Path(args.vault)
    # Over-fetch: navigation pages and multiple chunks of one paper both get
    # dropped below, so asking for exactly `--top` would under-deliver.
    hits = collapse(search(vault, args.query, max(args.top * 4, 20)))[:args.top]

    if not hits:
        print("无命中。")
        return 1

    print(f"「{args.query}」— {len(hits)} 篇\n")
    for rank, hit in enumerate(hits, start=1):
        page = Path(args.vault) / hit["page_path"]
        props = frontmatter(page)
        title = props.get("title") or page.stem
        page_type = props.get("type") or "?"
        print(f"{rank}. [{hit['bm25_score']:.1f}] {title[:78]}")

        # A method or concept page is synthesis, not a paper. Reporting "no
        # payload" for one would read as a retrieval failure when it is simply a
        # different kind of page.
        if page_type != "source":
            label = {"method": "方法页", "concept": "概念页"}.get(page_type, page_type)
            print(f"   {label} | status: {props.get('status') or '?'}")
        else:
            meta = [props.get("published") or "无日期", props.get("source") or "?"]
            if props.get("strategy_labels"):
                # Rule-inferred and measured to mislabel (8 of 9 known intraday
                # papers). Shown as a hint, never as a filter.
                meta.append(f"规则推断: {props['strategy_labels']}")
            print(f"   {' | '.join(meta)}")
            locator = props.get("fulltext_locator")
            if locator:
                chars = props.get("fulltext_chars") or "?"
                print(f"   全文 {chars} 字符 -> {locator}")
            else:
                print("   无全文载荷（抓取失败），只有标题与元数据")
        print(f"   页面 -> {hit['page_path']}")
        print()

    print("命中是指针不是答案：要判断细节，读上面的 .raw/captured/ 载荷。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
