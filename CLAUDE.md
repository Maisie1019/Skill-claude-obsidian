# 私人知识库协作规则

本仓库是 [claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian) 的 fork，加上一层私人使用配置。
Obsidian 保存可信材料和长期知识，Agent 负责分析、连接与维护，人负责判断和授权。

产品层的开发规范见 [AGENTS.md](AGENTS.md)；本文件是本机使用层，只在开发 checkout 中存在，不进入 release artifact。

## 两个独立位置

| 位置 | 角色 | git |
|---|---|---|
| `E:\Skills\obsidian-paper`（本仓库） | 产品层：skills、CLI、模板。跟随 upstream 更新 | 推送到 `origin` |
| `E:\Skills\obsidian-vault` | **私人知识库（vault）**：全部研究笔记与原始资料 | 不进任何远端 |

vault **必须**在本仓库之外。产品会对产品树内的 vault 路径直接拒绝写入
（`PLUGIN_TREE_IS_NOT_VAULT`，见 `claude_obsidian/paths.py`），以防可变知识被 upstream 更新覆盖。
vault 自带 `.gitignore`，本身可以单独做版本控制，但不要推到本 fork 的远端。

**不要修改 upstream 原有文件。** 本地定制一律以新增文件的方式进行，这样 `git pull upstream main` 永远不会产生冲突。
`upstream` 的 push 地址已禁用，只能 fetch。

## Vault 结构

vault 已通过官方 `adopt` 流程接入，采用产品标准结构：

- `inbox/`：可见的资料入口（`.claude-obsidian.json` 的 `source_inbox`）。
- `.raw/`：不可变原文载荷，仅可新增，不得改写或删除证据内容。
- `wiki/`：生成的知识页面。`index.md` 总索引、`overview.md` 概览、`log.md` 操作历史（新的在前）、`hot.md` 有界近期上下文。
- `wiki/meta/ledgers/`：来源台账与断言台账，保存权威性、时效、支持与矛盾、置信度、复核状态。
- `.vault-meta/`：运行时锁、日志、索引，已被忽略。

vault 中另有一套早期中文骨架（`00-收件箱`、`01-原始资料`、`02-知识维基`、`08-系统`、`Home.md`）。
它们是空模板，与上述结构重复。**在用户明确确认前不要删除或迁移它们**；新内容一律写入标准结构。
`08-系统/字段规范.md` 与 `Templates/` 中的中文模板仍可作为字段命名参考。

不要保存密码、Token、私钥、客户身份信息或其他敏感数据。发现疑似敏感信息时停止摘录，只报告文件和风险位置，不复述秘密值。

## 默认操作边界

Agent 默认只读：可以盘点、搜索、比较、分析并提出变更方案，但不得直接创建、移动或修改文件。

只有在用户明确确认写入范围后，才可以执行对应的创建、移动或修改。以下操作必须单独确认具体范围：

- 删除文件或证据内容；
- 覆盖原始资料；
- 批量改名；
- 调整目录结构；
- 合并笔记并移除旧页面；
- 将 AI 推断或冲突结论标记为 `verified` / 已解决。

一次确认只适用于当次明确描述的范围，不视为以后持续授权。

## 整理规则

1. 创建新页面前，按标题、别名、URL、作者、日期和关键概念搜索全库；同主题优先更新已有知识页。
2. `.raw/` 是一份来源的证据记录；`wiki/` 是跨来源或经过验证的长期综合。不得用摘要替换原文。
3. 内容必须明确标记为：`事实`、`外部观点`、`AI推断`、`个人判断`、`实测结果`。
4. 不得替用户编写"个人判断"；未获人工确认的 AI 生成内容只能标记为 `AI推断`。
5. 重要结论必须链接 `.raw/` 中的来源或实验记录，并在台账中登记。无法追溯的内容不得升级为 `verified`。
6. 新旧来源冲突时保留双方观点，在断言台账中登记矛盾，不得擅自覆盖或裁决。
7. 使用 Obsidian wikilink。链接应帮助理解关系，而不是为了增加链接数量。
8. 已授权写入完成后，更新相关知识页、内部链接、最窄相关索引和 `wiki/log.md`。

## 状态流程

`inbox -> triaged -> draft -> review -> verified -> archived`

Agent 可以建议状态变化，但只有人可以确认 `verified`、解决冲突或批准归档/删除。

## 运行命令

本机 `python3` 是 Microsoft Store 别名，不可用；Windows 侧一律用 `python`。

只读检查、dry-run、lint、检索在 Windows 原生可用：

```bash
python scripts/claude-obsidian.py doctor --vault "E:/Skills/obsidian-vault"
python scripts/claude-obsidian.py lint --vault "E:/Skills/obsidian-vault"
```

**所有 vault 写入必须在 WSL 中执行**（原生 Windows 返回 `UNSUPPORTED_PLATFORM`）。
已安装 Ubuntu（WSL2），且 `/etc/wsl.conf` 已设 `[automount] options = "metadata"`——
这是必需的：没有它，DrvFs 无法表达 `0600` 权限位，事务会以 `RESULT_DRIFT` 失败回滚。

```bash
wsl -d Ubuntu -u root -- bash -lc '
cd /mnt/e/Skills/obsidian-paper
python3 scripts/claude-obsidian.py <command> /mnt/e/Skills/obsidian-vault \
  --generated-at "<ISO-UTC>" --operation-id <id>'
```

审阅返回的计划后，用同一条命令追加 `--approved-plan-sha256 <hash> --apply` 执行。
审批哈希绑定生成它的环境：**dry-run 必须和 apply 在同一侧运行**，
Windows 侧产生的哈希在 WSL 中重放会报 `PLAN_CHANGED`。

中文骨架自带的校验器（针对旧结构，仍可用于中文目录）：

```bash
python .claude/skills/obsidian-knowledge-maintainer/scripts/validate_vault.py "E:/Skills/obsidian-vault"
```

## 完成报告

每次整理必须分别报告：新增文件、更新文件、重复或冲突、待确认事项、未执行事项及原因、校验结果。
