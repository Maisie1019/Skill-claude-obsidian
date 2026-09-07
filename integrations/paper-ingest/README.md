# paper-ingest — 量化论文日报 → Obsidian vault

本机集成层，把 `E:\Skills\daily_paper_report` 每日产出的论文接入知识库。

目录下所有文件都是**新增**的，不改动 upstream 任何文件，
因此 `git pull upstream main` 不会产生冲突。

## 数据流

```
daily_paper_report.py
  └─ obsidian_export.py            Windows，普通文件写入
       └─ vault/inbox/*.md         可见的资料入口
            └─ daily_sync.sh       WSL，产品事务
                 ├─ capture        → .raw/captured/<sha>.md   不可变、仅新增
                 ├─ ingest         → wiki/sources/*.md
                 │                   wiki/meta/ledgers/source-ledger.json
                 │                   wiki/index.md · hot.md · log.md
                 └─ lint
```

两个系统之间的接口是 `last_report_papers.json`（schema `daily-paper-report.export.v1`），
不是渲染后的 HTML。HTML 解析只用于一次性回补历史。

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
* 无新增来源时不写 `index` / `hot` / `log`，操作历史不会被空转污染。

## 前置条件

* WSL2 + Ubuntu，且 `/etc/wsl.conf` 设 `[automount] options = "metadata"`
  （否则 DrvFs 无法表达 `0600`，事务会以 `RESULT_DRIFT` 回滚）。
* vault 必须在本仓库之外，否则产品拒绝写入（`PLUGIN_TREE_IS_NOT_VAULT`）。
* Windows 侧只能做只读检查和 dry-run；写入一律在 WSL。
