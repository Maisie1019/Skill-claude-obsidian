#!/usr/bin/env python3
"""Build an `ingest` transaction bundle from paper notes staged in the vault inbox.

Local integration layer. This file is additive to the upstream product tree so
`git pull upstream main` never conflicts with it.

Scope, deliberately narrow
--------------------------
This builds only the *deterministic* half of an ingest:

  * one `wiki/sources/*.md` page per captured inbox paper note;
  * one source-ledger record per page, keyed by the core's canonical
    `stable_source_id`;
  * refreshed `wiki/index.md`, `wiki/log.md`, and `wiki/hot.md`.

It never writes the claim ledger and never asserts what a paper found. Claims
require reading the source and human judgement; a script that manufactured them
would be inventing evidence. Run `/claude-obsidian:wiki-ingest` for that.

Usage
-----
    python build_ingest_bundle.py --vault VAULT --out bundle.json \
        --operation-id ingest-papers-YYYYMMDD

Then review and apply with the core:

    python3 scripts/claude-obsidian.py transaction inspect bundle.json --vault VAULT
    python3 scripts/claude-obsidian.py transaction apply  bundle.json --vault VAULT \
        --approved-plan-sha256 <approval_sha256>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Sequence, Tuple

PRODUCT_ROOT = Path(__file__).resolve().parents[2]
if str(PRODUCT_ROOT) not in sys.path:
    sys.path.insert(0, str(PRODUCT_ROOT))

from claude_obsidian.ledgers import stable_source_id  # noqa: E402

SCHEMA = "claude-obsidian.transaction.v1"
SOURCE_SCHEMA = "claude-obsidian.source-ledger.v1"

# How long a captured research note stays fresh before it should be re-checked.
REFRESH_DAYS = 180

# Publisher host -> (authority, independence key). The captured payload is our
# own digest document, so authority describes the material it quotes, capped at
# `secondary`: a generated digest is never itself a primary record.
PUBLISHER_AUTHORITY: Dict[str, Tuple[str, str]] = {
    "arxiv.org": ("secondary", "arxiv"),
    "doi.org": ("secondary", "crossref"),
    "www.aqr.com": ("secondary", "aqr"),
    "aqr.com": ("secondary", "aqr"),
    "www.federalreserve.gov": ("secondary", "federalreserve"),
    "federalreserve.gov": ("secondary", "federalreserve"),
    "stratproof.com": ("community", "stratproof"),
}

_FM = re.compile(r"^---\n(.*?)\n---\n", re.S)
_UNSAFE = re.compile(r'[\\/:*?"<>|#^\[\]]')


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_frontmatter(text: str) -> Dict[str, Any]:
    """Parse the flat YAML frontmatter this pipeline writes.

    Only the shapes `obsidian_export.py` emits are supported: scalars and
    single-level `- ` lists. Anything else is ignored rather than guessed at.
    """
    match = _FM.match(text)
    if not match:
        return {}
    props: Dict[str, Any] = {}
    key: Optional[str] = None
    for line in match.group(1).splitlines():
        if line.startswith("  - ") and key:
            props.setdefault(key, [])
            if isinstance(props[key], list):
                props[key].append(_unquote(line[4:].strip()))
            continue
        if ":" not in line:
            continue
        raw_key, _, raw_value = line.partition(":")
        key = raw_key.strip()
        value = raw_value.strip()
        props[key] = True if value == "" else _coerce(value)
    return props


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return value


def _coerce(value: str) -> Any:
    if value in ("true", "false"):
        return value == "true"
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return _unquote(value)


def extract_section(text: str, heading: str) -> Optional[str]:
    """Return the body of one `## heading` section, without its label line."""
    pattern = re.compile(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", re.S | re.M)
    match = pattern.search(text)
    if not match:
        return None
    body = match.group(1).strip()
    body = re.sub(r"^`[^`]+`\s*", "", body).strip()
    return body or None


_LEAD_META = re.compile(r"^(抓取方式：|全文存档：|以下句子来自原文)")


def strip_lead_meta(body: Optional[str]) -> Optional[str]:
    """Drop the inbox note's own header lines from a copied verbatim block.

    Those lines carry a wikilink into `inbox/fulltext/`, which resolves from the
    note but not from `wiki/sources/`. The source page states the payload path in
    its own meta block instead, so the pointer survives without a broken link.
    """
    if not body:
        return None
    lines = body.splitlines()
    while lines and (not lines[0].strip() or _LEAD_META.match(lines[0].strip())):
        lines.pop(0)
    return "\n".join(lines).strip() or None


def host_of(url: str) -> str:
    from urllib.parse import urlsplit

    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def safe_page_name(title: str) -> str:
    name = _UNSAFE.sub(" ", title or "").strip()
    name = re.sub(r"\s+", " ", name)
    return (name[:90].rstrip() or "Untitled")


def yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


# --------------------------------------------------------------------------
# page rendering
# --------------------------------------------------------------------------

def render_source_page(props: Dict[str, Any], abstract: Optional[str],
                       locator: str, source_id: str, today: str,
                       excerpts: Optional[str] = None,
                       quant: Optional[str] = None,
                       fulltext_locator: Optional[str] = None) -> str:
    title = props.get("title") or "Untitled"
    lines = [
        "---",
        "type: source",
        f"title: {yaml_scalar(title)}",
        "status: draft",
        f"created: {today}",
        f"updated: {today}",
        f"source_id: {yaml_scalar(source_id)}",
        f"raw_locator: {yaml_scalar(locator)}",
    ]
    for key in ("url", "source", "journal", "published", "report_date",
                "priority", "strategy_labels", "asset_scope", "holding_horizon"):
        if props.get(key):
            lines.append(f"{key}: {yaml_scalar(props[key])}")
    lines.append(f"evidence_class: {yaml_scalar(props.get('evidence_class') or '规则推断')}")
    lines.append(f"has_abstract: {'true' if abstract else 'false'}")
    lines.append(f"has_fulltext: {'true' if excerpts else 'false'}")
    for key in ("fulltext_method", "fulltext_chars"):
        if props.get(key):
            lines.append(f"{key}: {yaml_scalar(props[key])}")
    if fulltext_locator:
        lines.append(f"fulltext_locator: {yaml_scalar(fulltext_locator)}")
    authors = props.get("authors")
    if isinstance(authors, list) and authors:
        lines.append("authors:")
        lines.extend(f"  - {yaml_scalar(a)}" for a in authors)
    lines.append("tags:")
    lines.extend(["  - source", "  - paper", "  - quant-research"])
    lines.append("---")
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")

    meta: List[str] = []
    if props.get("url"):
        meta.append(f"- 原文：<{props['url']}>")
    if isinstance(authors, list) and authors:
        meta.append(f"- 作者：{', '.join(authors)}")
    if props.get("source"):
        meta.append(f"- 来源：{props['source']}"
                    + (f" / {props['journal']}" if props.get("journal") else ""))
    if props.get("published"):
        meta.append(f"- 发表：{props['published']}")
    meta.append(f"- 不可变载荷：`{locator}`")
    if fulltext_locator:
        meta.append(f"- 全文载荷：`{fulltext_locator}`")
    meta.append(f"- 来源标识：`{source_id}`")
    lines.extend(meta)
    lines.append("")

    if abstract:
        lines.append("## 原文摘要")
        lines.append("")
        lines.append("`外部观点` — 以下为原文摘要逐字保留，未经改写。")
        lines.append("")
        lines.append("> " + abstract.replace("\n", "\n> "))
        lines.append("")
    elif not excerpts:
        lines.append("## 原文摘要")
        lines.append("")
        lines.append("> [!warning] 未取得原文")
        lines.append("> 该来源的摘要与全文均无法从公开页面或 Crossref 取得。"
                     "本页仅保留可核验的元数据，不含任何结论性内容。")
        lines.append("")

    # Verbatim material carried over from the inbox note. Copied, not re-derived:
    # the point of these blocks is that they are the paper's own words.
    if excerpts:
        lines.append("## 原文章节摘录")
        lines.append("")
        lines.append(excerpts)
        lines.append("")
    if quant:
        lines.append("## 可核验陈述（含数值或指标）")
        lines.append("")
        lines.append(quant)
        lines.append("")

    lines.append("## 待人工判断")
    lines.append("")
    lines.append("- [ ] 阅读原文，确认摘要之外的方法与样本细节")
    lines.append("- [ ] 决定是否值得升级为知识页并登记断言")
    lines.append("- [ ] 若登记断言，需在断言台账中给出支持证据与置信度")
    lines.append("")
    lines.append("相关：[[index|知识库索引]]")
    lines.append("")
    return "\n".join(lines)


DEFAULT_TAIL_SECTIONS = (
    "## Concepts\n\n- No concepts indexed yet.\n\n"
    "## Entities\n\n- No entities indexed yet.\n\n"
    "## Questions\n\n- No questions indexed yet.\n"
)


def index_tail(existing: str) -> str:
    """Return everything from `## Concepts` onward, unchanged.

    This pipeline owns the `## Sources` catalog and nothing else. Concepts,
    entities, and questions are written by `wiki-ingest` when a human decides a
    source is worth synthesizing; regenerating them from the inbox would delete
    that work on the next nightly run. Carry them through verbatim instead.
    """
    index = existing.find("\n## Concepts")
    if index == -1:
        return DEFAULT_TAIL_SECTIONS
    return existing[index + 1:].rstrip() + "\n"


def render_index(pages: Sequence[Tuple[str, str]], today: str,
                 existing: str = "") -> str:
    lines = [
        "---", "type: meta", "title: Wiki Index", "status: evergreen",
        "created: 2026-09-05", f"updated: {today}",
        "tags:", "  - meta", "  - index", "---", "",
        "# Wiki Index", "",
        "This catalog is updated by completed knowledge operations.", "",
        "## Sources", "",
    ]
    for name, title in sorted(pages, key=lambda item: item[1].lower()):
        lines.append(f"- [[{name}|{title}]]")
    return "\n".join(lines) + "\n\n" + index_tail(existing)


def render_log(existing: str, entry: str) -> str:
    """Prepend one entry; newest first, per the vault's log convention."""
    match = _FM.match(existing)
    head = match.group(0) if match else ""
    body = existing[len(head):] if head else existing
    body = body.lstrip("\n")
    title_line = ""
    if body.startswith("# "):
        first, _, rest = body.partition("\n")
        title_line = first + "\n"
        body = rest.lstrip("\n")
    return f"{head}{title_line}\n{entry}\n\n{body}".rstrip() + "\n"


def render_hot(pages: Sequence[Tuple[str, str]], today: str) -> str:
    lines = [
        "---", "type: meta", "title: Hot Cache", "status: evergreen",
        "created: 2026-09-05", f"updated: {today}",
        "tags:", "  - meta", "  - hot", "---", "",
        "# Hot Cache", "",
        f"最近一次知识操作：{today}（量化论文日报接入）。", "",
    ]
    for name, title in sorted(pages, key=lambda item: item[1].lower()):
        lines.append(f"- [[{name}|{title}]]")
    lines.append("")
    return "\n".join(lines)


def merged_pages(prior: Dict[str, Any], page_path: str) -> List[str]:
    """Keep the source page first, then any page `wiki-ingest` attached later.

    This pipeline rebuilds every record it owns from the inbox on each run. Left
    alone that would silently drop a concept page a human linked to this source,
    which is exactly the kind of quiet deletion the ledger exists to prevent.
    """
    extra = [p for p in (prior.get("pages") or []) if p != page_path]
    return [page_path] + extra


# --------------------------------------------------------------------------
# bundle
# --------------------------------------------------------------------------

def build(vault: Path, operation_id: str, today: str,
          refresh_pages: bool = False) -> Dict[str, Any]:
    inbox = vault / "inbox"
    captured = vault / ".raw" / "captured"
    ledger_path = vault / "wiki" / "meta" / "ledgers" / "source-ledger.json"

    notes = sorted(p for p in inbox.glob("*.md"))
    if not notes:
        raise SystemExit("inbox 中没有 .md 文件。")

    # Full-text archives live in `inbox/fulltext/` and are keyed back to their
    # note by the `paper_note` field, so a page can cite its own payload.
    archives: Dict[str, Tuple[str, str]] = {}
    for archive in sorted((inbox / "fulltext").glob("*.md")):
        raw = archive.read_bytes()
        digest = sha256_bytes(raw)
        if not (captured / f"{digest}.md").exists():
            raise SystemExit(
                f"{archive.name} 尚未 capture（缺 .raw/captured/{digest}.md）。"
            )
        note_stem = parse_frontmatter(raw.decode("utf-8")).get("paper_note")
        if note_stem:
            archives[str(note_stem)] = (digest, f".raw/captured/{digest}.md")

    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    sources: Dict[str, Any] = dict(ledger.get("sources") or {})

    writes: List[Dict[str, Any]] = []
    expected: Dict[str, Optional[str]] = {}
    index_pages: List[Tuple[str, str]] = []
    summary: List[str] = []
    new_pages = 0
    refreshed = 0
    # page path -> note that claimed it. Two inbox notes can land on the same
    # page: the same paper reached the report twice under titles that differ
    # only in a journal suffix, or two long titles agree on their first 90
    # characters. Either way a second write to that path is a duplicate, and
    # the transaction engine rejects the whole bundle over it.
    claimed: Dict[str, str] = {}
    duplicates: List[Tuple[str, str]] = []

    # Pages already recorded in the ledger stay in the index even after their
    # inbox note is archived, so archiving never orphans a published page.
    for record in sources.values():
        for page in record.get("pages") or []:
            if page.startswith("wiki/sources/") and (vault / page).exists():
                name = PurePosixPath(page).stem
                index_pages.append((name, str(record.get("title") or name)))

    refresh_due = (date.fromisoformat(today) + timedelta(days=REFRESH_DAYS)).isoformat()

    # Source ids that the current inbox state produces, per page. Anything else
    # still marked `active` for one of these pages is an earlier version of the
    # same payload, left behind when a note was regenerated.
    current_ids: Dict[str, List[str]] = {}

    for note in notes:
        raw = note.read_bytes()
        text = raw.decode("utf-8")
        props = parse_frontmatter(text)
        if props.get("source_type") != "paper":
            continue

        payload_hash = sha256_bytes(raw)
        locator = f".raw/captured/{payload_hash}.md"
        if not (captured / f"{payload_hash}.md").exists():
            raise SystemExit(
                f"{note.name} 尚未 capture（缺 {locator}）。先运行 capture apply。"
            )

        source_id = stable_source_id("file", locator, payload_hash)
        authority, independence = PUBLISHER_AUTHORITY.get(
            host_of(str(props.get("url") or "")), ("unknown", "unknown")
        )
        abstract = extract_section(text, "原文摘要（未改写）")
        excerpts = strip_lead_meta(extract_section(text, "原文章节摘录（逐字）"))
        quant = strip_lead_meta(extract_section(text, "可核验陈述（逐字，含数值或指标）"))

        archive_hash, fulltext_locator = archives.get(note.stem, (None, None))

        page_name = safe_page_name(str(props.get("title") or note.stem))
        page_path = f"wiki/sources/{page_name}.md"
        title = str(props.get("title") or page_name)

        if page_path in claimed:
            # Keep the note that got here first — `notes` is sorted, so the
            # winner is the same on every run — and report the rest. Merging
            # them is a judgement about whether they really are one paper, and
            # deleting the loser destroys evidence; neither belongs in a
            # nightly script. The skipped note's payload stays in
            # `.raw/captured/`, so nothing is lost by leaving it for a human.
            duplicates.append((note.name, claimed[page_path]))
            continue
        claimed[page_path] = note.name
        index_pages.append((page_name, title))

        current = vault / page_path
        content = render_source_page(props, abstract, locator, source_id, today,
                                     excerpts, quant, fulltext_locator)
        encoded = content.encode("utf-8")
        marks = "有全文" if excerpts else ("有摘要" if abstract else "无原文")

        if not current.exists():
            writes.append({"path": page_path, "mode": "create", "content": content,
                           "sha256": sha256_bytes(encoded)})
            expected[page_path] = None
            new_pages += 1
            summary.append(f"新增，{marks} | {page_name}")
        elif refresh_pages and current.read_bytes() != encoded:
            # Opt-in only, and it overwrites the whole page: any human annotation
            # on it is lost. The caller has to ask for this explicitly.
            writes.append({"path": page_path, "mode": "replace", "content": content,
                           "sha256": sha256_bytes(encoded)})
            expected[page_path] = sha256_bytes(current.read_bytes())
            refreshed += 1
            summary.append(f"重写，{marks} | {page_name}")
        else:
            # Re-runs must not clobber a page a human has since annotated. An
            # existing page is left exactly as it is; only its ledger record is
            # refreshed, which is safe because the payload is content-addressed.
            summary.append(f"已存在，保留 | {page_name}")

        if archive_hash and fulltext_locator:
            # The verbatim archive is its own piece of evidence and gets its own
            # ledger record, pointing at the same page. It shares the paper's
            # independence key: one paper, not two corroborating sources.
            archive_id = stable_source_id("file", fulltext_locator, archive_hash)
            current_ids.setdefault(page_path, []).append(archive_id)
            prior = sources.get(archive_id) or {}
            sources[archive_id] = {
                "origin": {"kind": "file", "locator": fulltext_locator},
                "title": f"{title}（全文逐字存档）",
                "content_kind": "document",
                "authority": authority,
                "review_status": "active",
                "content_sha256": archive_hash,
                "ingested_at": prior.get("ingested_at") or today,
                "retrieved_at": today,
                "refresh_due": refresh_due,
                "independence_key": independence,
                "pages": merged_pages(prior, page_path),
                "supersedes": prior.get("supersedes"),
            }

        current_ids.setdefault(page_path, []).append(source_id)
        previous = sources.get(source_id) or {}
        sources[source_id] = {
            "origin": {"kind": "file", "locator": locator},
            "title": title,
            "content_kind": "document",
            "authority": authority,
            "review_status": "active",
            "content_sha256": payload_hash,
            # First sighting is the real ingest date; later runs only re-observe.
            "ingested_at": previous.get("ingested_at") or today,
            "retrieved_at": today,
            "refresh_due": refresh_due,
            "independence_key": independence,
            "pages": merged_pages(previous, page_path),
            "supersedes": previous.get("supersedes"),
        }

    # Regenerating a note changes its bytes, so the payload is content-addressed
    # to a new source id and the old record would sit there `active` forever —
    # inflating the apparent support behind any claim that cites the page. Retire
    # them instead of deleting: `superseded` keeps the audit trail, and the
    # payload under `.raw/captured/` is untouched either way.
    #
    # Scope is deliberately tight. Only records this pipeline could have written
    # are touched: origin kind `file`, a captured payload, and exactly one page,
    # which is a page the current run rendered.
    ARCHIVE_MARK = "（全文逐字存档）"
    retired = 0
    # (page, is_archive) -> most recent retired id, so the surviving record can
    # point back at the version it replaced and the chain stays walkable.
    newest_retired: Dict[Tuple[str, bool], Tuple[str, str]] = {}
    for stale_id, record in sources.items():
        if record.get("review_status") != "active":
            continue
        pages = record.get("pages") or []
        if len(pages) != 1 or pages[0] not in current_ids:
            continue
        if stale_id in current_ids[pages[0]]:
            continue
        origin = record.get("origin") or {}
        if origin.get("kind") != "file":
            continue
        if not str(origin.get("locator") or "").startswith(".raw/captured/"):
            continue
        sources[stale_id] = {**record, "review_status": "superseded"}
        retired += 1
        key = (pages[0], ARCHIVE_MARK in str(record.get("title") or ""))
        stamp = str(record.get("ingested_at") or "")
        if key not in newest_retired or stamp >= newest_retired[key][1]:
            newest_retired[key] = (stale_id, stamp)

    for page_path, ids in current_ids.items():
        for source_id in ids:
            record = sources[source_id]
            if record.get("supersedes"):
                continue
            key = (page_path, ARCHIVE_MARK in str(record.get("title") or ""))
            if key in newest_retired:
                record["supersedes"] = newest_retired[key][0]

    if retired:
        summary.append(f"\n退役旧版本来源记录 {retired} 条（标记 superseded，载荷保留）。")

    if duplicates:
        summary.append(f"\n重复页名 {len(duplicates)} 条，已跳过，需人工判断是否同一篇：")
        for skipped_note, kept_note in duplicates:
            summary.append(f"  跳过 {skipped_note}\n    保留 {kept_note}")

    index_pages = sorted(set(index_pages))

    def replace_if_changed(rel: str, content: str) -> None:
        """Queue a replace only when the bytes actually differ.

        A no-op rewrite would still churn the ledger's `generated_at` and the
        log, making every run look like a change. Skipping keeps the operation
        history meaningful.
        """
        current = (vault / rel).read_bytes()
        encoded = content.encode("utf-8")
        if current == encoded:
            return
        writes.append({"path": rel, "mode": "replace", "content": content,
                       "sha256": sha256_bytes(encoded)})
        expected[rel] = sha256_bytes(current)

    # The ledger is rewritten whenever its records actually change — a refreshed
    # `retrieved_at` alone is not worth a transaction, but a new record is.
    if sources != (ledger.get("sources") or {}) and (new_pages or refreshed or retired):
        rel_ledger = "wiki/meta/ledgers/source-ledger.json"
        ledger_out = {
            "schema": SOURCE_SCHEMA,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sources": sources,
        }
        ledger_text = json.dumps(
            ledger_out, ensure_ascii=False, indent=2, sort_keys=True
        ) + "\n"
        writes.append({"path": rel_ledger, "mode": "replace", "content": ledger_text,
                       "sha256": sha256_bytes(ledger_text.encode("utf-8"))})
        expected[rel_ledger] = sha256_bytes(ledger_path.read_bytes())

    if new_pages or refreshed or retired:
        replace_if_changed("wiki/index.md", render_index(
            index_pages, today,
            (vault / "wiki" / "index.md").read_text(encoding="utf-8"),
        ))
        replace_if_changed("wiki/hot.md", render_hot(index_pages, today))

        log_path = vault / "wiki" / "log.md"
        entry = (
            f"## {today} — 量化论文日报接入\n\n"
            f"- 操作：`{operation_id}`\n"
            f"- 新增来源页 {new_pages} 个，重写 {refreshed} 个，"
            f"退役旧版本来源记录 {retired} 条；"
            f"索引共 {len(index_pages)} 个来源页。\n"
            f"- 断言台账未改动：尚无经人工核验的断言。\n"
            f"- 来源载荷位于 `.raw/captured/`，create-only。\n"
        )
        replace_if_changed(
            "wiki/log.md", render_log(log_path.read_text(encoding="utf-8"), entry)
        )

    print("\n".join(summary))
    print(f"\n新增来源页 {new_pages} 个，重写 {refreshed} 个，"
          f"退役 {retired} 条，共 {len(writes)} 个写入。")

    return {
        "schema": SCHEMA,
        "operation_id": operation_id,
        "operation_type": "ingest",
        "expected_hashes": expected,
        "writes": writes,
        "address_requests": [],
        "source_manifest_updates": {},
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vault", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--today", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument(
        "--refresh-pages", action="store_true",
        help="重写内容已变化的既有来源页。会覆盖页面上的人工批注，需明确授权。",
    )
    args = parser.parse_args(argv)

    bundle = build(Path(args.vault), args.operation_id, args.today,
                   refresh_pages=args.refresh_pages)
    if not bundle["writes"]:
        print("没有新的来源需要接入。")
        # Distinct from success so a caller can skip the transaction entirely
        # rather than submitting an empty one.
        return 3
    Path(args.out).write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    print(f"已写出 bundle：{args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
