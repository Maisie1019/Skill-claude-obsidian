# paper-ingest — 量化论文日报 → Obsidian vault

本机集成层，把 `E:\Skills\daily_paper_report` 每日产出的论文接入知识库。

目录下所有文件都是**新增**的，不改动 upstream 任何文件，
因此 `git pull upstream main` 不会产生冲突。

## 数据流

```
daily_paper_report.py
  └─ paper_fulltext.py             联网取回论文本身（arXiv / 出版方 / Crossref）
       └─ obsidian_export.py       Windows，普通文件写入
            ├─ vault/inbox/*.md              可见的资料入口（含逐字摘录）
            └─ vault/inbox/fulltext/*.md     全文逐字存档
                 └─ daily_sync.sh  WSL，产品事务
                      ├─ capture   → .raw/captured/<sha>.md   不可变、仅新增
                      ├─ ingest    → wiki/sources/*.md
                      │              wiki/meta/ledgers/source-ledger.json
                      │              wiki/index.md · hot.md · log.md
                      └─ lint
```

两个系统之间的接口是 `last_report_papers.json`（schema `daily-paper-report.export.v1`），
不是渲染后的 HTML。HTML 解析只用于一次性回补历史。

## 原文取回

来源页上的正文一律**逐字**取自论文本身，不做改写或概括——
概括正是此前那批"只有推断、没有原文"的笔记的成因。

| 站点 | 路径 |
|---|---|
| arXiv | Atom API 取元数据 → `arxiv.org/html/<id>`（LaTeXML，真实章节边界）→ PDF |
| DOI | 出版方落地页优先，Crossref 仅作元数据兜底 |
| 其他白名单站点 | 直接抓页面，按标题层级切章节 |

Atom API 被限流时（429）不影响取回：渲染页由不同基础设施提供，
缺元数据也照抓正文，方式字段会记为 `arxiv+html` 而非 `arxiv-api+html`。
MathML 被折叠回 LaTeX 源码（`alttext`），否则一条公式会展开成几十行散字。

取回失败时来源页明写"未取得原文"，不用模板文字填充。

`inbox/fulltext/` 里的存档就是缓存：已有存档的论文不再联网重取。
抽取逻辑改进后要重取，用 `obsidian_export.py --from-inbox --fetch-fulltext --refetch --overwrite`。

## 边界：这里不写断言

自动化只产出**可机械核验**的东西：原文摘要的逐字保留、内容寻址的载荷、来源台账记录。

`claim-ledger.json` 永远不由脚本写入，来源页状态固定为 `draft`。
断言"这篇论文证明了什么"需要读原文，那是人的判断；
脚本代写断言等于伪造证据。升级为知识页与登记断言走 `/claude-obsidian:wiki-ingest`。

同理，来源页的 `authority` 上限为 `secondary`：`.raw/captured/` 里的载荷是
本流水线生成的摘录文档，即使逐字引用了一手摘要，它本身也不是一手记录。

## 文件

| 文件 | 作用 |
|---|---|
| `build_ingest_bundle.py` | 扫描 inbox，生成 `ingest` 事务 bundle。退出码 `3` = 无新增 |
| `daily_sync.sh` | capture → ingest → lint。缺省 dry-run，`--apply` 执行 |
| `selftest.sh` | 在 `/tmp` 临时 vault 上跑通完整 apply 路径，不碰真实知识库 |

## 用法

```bash
# 预览（不改动任何文件）
wsl -d Ubuntu -u root -- bash /mnt/e/Skills/obsidian-paper/integrations/paper-ingest/daily_sync.sh

# 执行
wsl -d Ubuntu -u root -- bash /mnt/e/Skills/obsidian-paper/integrations/paper-ingest/daily_sync.sh --apply

# 重写既有来源页（抽取逻辑改进后用；会覆盖页面上的人工批注）
wsl -d Ubuntu -u root -- bash /mnt/e/Skills/obsidian-paper/integrations/paper-ingest/daily_sync.sh --apply --refresh-pages

# 自检
wsl -d Ubuntu -u root -- bash /mnt/e/Skills/obsidian-paper/integrations/paper-ingest/selftest.sh
```

日报跑完后自动触发由 `daily_paper_report/config.json` 控制：

```json
"obsidian": {
  "enabled": true,
  "vault_path": "E:/Skills/obsidian-vault",
  "inbox_subdir": "inbox",
  "auto_sync": true,
  "sync_distro": "Ubuntu",
  "sync_script": "/mnt/e/Skills/obsidian-paper/integrations/paper-ingest/daily_sync.sh"
}
```

`auto_sync` 缺省为 `false`。同步失败不会影响日报：资料已在 `inbox/`，下次运行会重新接入。

## 幂等性

* 载荷内容寻址：inbox 文档未变 → capture 零写入。
* 已存在的来源页不会被覆盖，人工批注得以保留；只刷新其台账记录的 `retrieved_at`。
  唯一例外是显式的 `--refresh-pages`。
* 无新增来源时不写 `index` / `hot` / `log`，操作历史不会被空转污染。
* 全文存档单独登记一条来源记录，`pages` 指向同一个来源页，
  `independence_key` 与论文相同——同一篇论文不该被算作两个互相印证的来源。

## 前置条件

* WSL2 + Ubuntu，且 `/etc/wsl.conf` 设 `[automount] options = "metadata"`
  （否则 DrvFs 无法表达 `0600`，事务会以 `RESULT_DRIFT` 回滚）。
* vault 必须在本仓库之外，否则产品拒绝写入（`PLUGIN_TREE_IS_NOT_VAULT`）。
* Windows 侧只能做只读检查和 dry-run；写入一律在 WSL。
