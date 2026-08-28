---
name: meme-safety
description: >
  Meme 红线闸门。检查 Top10 集中度、洗盘标记、蜜罐/冻结/增发（有数据才判）。
  任何一条红线命中则淘汰，不再做叙事。用户说这个币安不安全、能不能碰、蜜罐、rug、红线、技术分淘汰时使用。
  是单币研判工作流的第一步，失败即停止。
---
# meme-safety

> 回答框架第五节：**别被骗吗？** 技术分不达标直接淘汰，不进入叙事。

## 红线（框架原文）

- 合约可增发 / 可冻结 / 蜜罐
- LP 未锁 / dev 持仓 >5% 未 renounce
- Top10 持仓 > 30%
- 明显洗盘交易
- dev 连环 rug 前科

查不到的写入 `unchecked`，**不要写成 pass 完胜**。工作室发币数量是警示不是红线（见张雪机车案例）。

## 怎么跑

优先复用 holder 刚拉过的 JSON，避免重复请求：

```bash
python3 skills/meme-safety/evaluate_safety.py \
  --holders-raw skills/sol-holder-analysis/data/holder_analysis_*.json \
  --out skills/_shared/runs/safety.json
```

有 token info / security 原始 JSON 时一并传入 `--info`，才能判蜜罐和 mint。

合并进信封：

```bash
python3 skills/_shared/merge_envelope.py \
  --envelope skills/_shared/runs/envelope.json \
  --safety skills/_shared/runs/safety.json \
  --out skills/_shared/runs/envelope.json
```

## 编排约定

`safety.pass === false` → 工作流停止，只输出淘汰原因。
`unchecked` 非空 → 在报告红线节列出「未检查」，询问用户是否继续。
