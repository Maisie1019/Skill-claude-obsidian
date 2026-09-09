# `type: method` 页面 schema

产品文档允许自定义页型，前提是 schema 有文档：

> Core generated page types are `source`, `entity`, `concept`, `comparison`,
> `question`, `overview`, and `meta`. A custom scaffold may add types when its
> schema is documented.
> — `skills/wiki/references/frontmatter.md`

本文件就是那份文档。方法页放在 `wiki/methods/`。

## 为什么需要这个页型

来源页回答"这篇论文说了什么"，概念页回答"关于某个主题，各来源合起来说明了什么"。
两者都以**论文**为组织单位，所以第 18 篇强化学习论文进来时，你还是得从头读一遍。

方法页以**方法**为组织单位，把跨论文重复出现的东西沉淀下来：参数怎么取、
坑在哪里、复现要几步。它是这套知识库里唯一会随论文增多而**变得更省时间**的页型——
其余页型都是随论文增多而变多。

## Frontmatter

```yaml
---
type: method
title: "人类可读的方法名"
status: draft            # draft -> developing -> mature；verified 只有人能确认
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags:
  - method
method_id: kebab-case-id   # 稳定标识，重命名标题时不变
evidence_class: AI推断      # 综合部分的来源标注；见 CLAUDE.md 的五种标记
sources_core: 0            # 本库中把它当核心方法的论文数
sources_total: 0           # 本库中提及它的论文数
---
```

`sources_core` 与 `sources_total` 用提及次数分档得出，是**粗筛不是判断**：

| 档 | 判据 | 含义 |
|---|---|---|
| 核心 | 全文提及 ≥10 次 | 论文的主要方法 |
| 使用 | 2–9 次 | 用到但不是主线 |
| 提及 | 1 次 | 相关工作里带一句，**不计入 `sources_total`** |

## 正文结构

固定七节。空着比编造好——"本库尚无证据"本身就是有用的信息。

1. **一句话定位** — 这个方法解决什么问题。
2. **何时用 / 何时不该用** — 适用边界。
3. **数据与实现要求** — 频率、字段、算力。决定一个方法能不能进你的流程，
   往往是这一节而不是效果。
4. **本库证据** — 表格：论文 / 关键参数 / 报告口径。每格要么逐字引自全文载荷，
   要么写"原文未给出"。这一节必须可回溯。
5. **已知陷阱** — **严格分两类**：
   - `本库来源指出`：引用具体论文的原话，可回溯；
   - `通用方法学`：教科书常识，**不是本库来源**，必须显式标注，
     不得与前一类混排。
6. **复现检查清单** — 可勾选，用来核对一个新策略有没有踩坑。
7. **待人工判断** — 未决问题。

## 纪律

- 综合部分标 `AI推断`，未经人工核验不得升级。
- 关于某篇论文的具体陈述必须能回到 `.raw/captured/` 的载荷。
- 方法页**不产生断言台账记录**。断言是"某事为真"，方法页是"这样做"，两者不同。
  若方法页引出了可检验的断言，单独在台账登记并链接过来。
- 不要用来源页的 `strategy_labels` / `holding_horizon` 做归类：
  这两个字段是正则推断，实测 9 篇明显日内/微观结构的论文里 8 篇标错。
  方法归属按全文实测，不按标签。
