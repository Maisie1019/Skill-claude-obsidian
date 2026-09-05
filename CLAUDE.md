# 私人知识库协作规则

本仓库是 [claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian) 的 fork，加上一层私人知识库配置。
Obsidian 保存可信材料和长期知识，Agent 负责分析、连接与维护，人负责判断和授权。

产品层的开发规范见 [AGENTS.md](AGENTS.md)；本文件是本机使用层，只在开发 checkout 中存在，不进入 release artifact。

## 仓库布局

| 路径 | 归属 | 是否进 git |
|---|---|---|
| `skills/`、`claude_obsidian/`、`scripts/`、`templates/`、`docs/` | upstream 产品层，跟随 upstream 更新 | 是 |
| `.claude/skills/obsidian-knowledge-maintainer/` | 自建 skill：中文 vault 的整理与校验 | 是 |
| `CLAUDE.md` | 本文件，私人使用层规则 | 是 |
| `vault/` | **私人知识库内容** | **否** |

`vault/` 由 `.git/info/exclude` 排除。研究笔记、原始资料、实验记录一律不推送到任何远端仓库。
新增笔记目录时不需要改 `.gitignore`——它已整目录排除。

**不要修改 upstream 原有文件。** 本地定制一律以新增文件的方式进行，这样 `git pull upstream main` 永远不会产生冲突。

## Vault 目录职责

`vault/` 使用中文结构，不是 upstream 的 `wiki/` + `.raw/` 布局：

- `vault/00-收件箱`：等待处理的资料入口。
- `vault/01-原始资料`：保存原文、来源与实验记录；不得改写或删除证据内容。
- `vault/02-知识维基`：保存由一个或多个来源综合形成、可长期复用的知识。
- `vault/08-系统`：保存字段规范、工作流程、索引、模板、冲突、待确认事项和运行日志。

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
2. 原始资料是一份来源的证据记录；知识维基是跨来源或经过验证的长期综合。不得用摘要替换原文。
3. 内容必须明确标记为：`事实`、`外部观点`、`AI推断`、`个人判断`、`实测结果`。
4. 不得替用户编写"个人判断"；未获人工确认的 AI 生成内容只能标记为 `AI推断`。
5. 重要结论必须链接 `01-原始资料` 中的来源或实验记录。无法追溯的内容不得升级为 `verified`。
6. 新旧来源冲突时保留双方观点，登记到 `vault/08-系统/冲突登记.md`，不得擅自覆盖或裁决。
7. 使用 Obsidian wikilink。链接应帮助理解关系，而不是为了增加链接数量。
8. 已授权写入完成后，更新相关知识页、内部链接、最窄相关索引和运行日志。
9. 结构性修改后运行校验（见下）。

## 状态流程

`inbox -> triaged -> draft -> review -> verified -> archived`

Agent 可以建议状态变化，但只有人可以确认 `verified`、解决冲突或批准归档/删除。

## 校验

```bash
python .claude/skills/obsidian-knowledge-maintainer/scripts/validate_vault.py vault
```

本机 `python3` 是 Microsoft Store 别名，不可用；一律使用 `python`。
校验器检查 YAML 必填字段、枚举值、重复 ID、来源引用和内部链接；它不替代人工判断内容真假。

## 平台限制（Windows）

upstream 的 Python 写入链路（`claude-obsidian.py` 的 `init` / `adopt` / `transaction apply` / `capture apply` / `mode set`）
在原生 Windows 上会以 `UNSUPPORTED_PLATFORM` 拒绝执行，必须在 WSL 中运行；本机 WSL 尚未安装发行版。
只读检查与 dry-run 可以原生运行。`skills/` 下的 Markdown 技能不受此限制，Claude Code 可直接使用。

因此当前对 `vault/` 的写入走常规文件编辑 + 上述校验脚本，不走 upstream 的事务链路。

## 完成报告

每次整理必须分别报告：新增文件、更新文件、重复或冲突、待确认事项、未执行事项及原因、校验结果。
