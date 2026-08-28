---
name: meme-workflow
description: >
  Meme 分析编排器。按配方组合原子 skill：单币研判、发现流水线、概念扫描，或用户点名只跑某一块。
  用户说分析这个 meme、这个币能不能碰、帮我找新币、现在什么梗在爆发、meme 研判时使用本 skill。
  本 skill 自己不取数，只决定调用顺序、合并信封、套输出模板。
---
# meme-workflow

> 自己不拉链。原子块：`meme-safety`、`meme-holders`、`meme-stage`。
> 信封：`skills/_shared/envelope.md`。

工作目录：本仓库 `skills/`。

## 先识别配方

| 用户意图 | 配方 |
|----------|------|
| 合约 / 币名 / 能不能碰 | A 单币研判 |
| 帮我找新币、trenches、meme rush | B 发现（先列候选，再对幸存者跑 A 的简化版） |
| 什么梗在爆发、概念热度 | C 概念扫描 |
| 只要真人 / bundler / 红线 / 阶段 | 只跑对应原子块 |

默认链：未指定时 Solana；地址以 `0x` 开头则 BSC。用户说 Robinhood / pump.fun 的 `0x` 合约 → `--chain robinhood`，不要当成 BSC。

## 配方 A · 单币研判

```
1. meme-holders   → 原始 JSON
2. meme-safety --holders-raw 该 JSON
     fail → 停止，只报淘汰原因
     unchecked 非空 → 在红线节写明，询问是否继续
3. merge_envelope.py --holders-raw --safety
4. meme-stage --envelope
5. merge --stage
6. 按红线、阶段、仓位含义输出（阶段必须出现在结论里）
```

命令骨架：

```bash
python3 meme-holders/dispatch.py --address <ADDR>
# 记下「详细结果: ...json」

python3 meme-safety/evaluate_safety.py --holders-raw <该json> --out _shared/runs/safety.json
python3 _shared/merge_envelope.py --holders-raw <该json> --safety _shared/runs/safety.json --out _shared/runs/envelope.json
python3 meme-stage/judge_stage.py --envelope _shared/runs/envelope.json --out _shared/runs/stage.json
python3 _shared/merge_envelope.py --envelope _shared/runs/envelope.json --stage _shared/runs/stage.json --out _shared/runs/envelope.json
```

可剪枝：用户只要筹码 → 停在步骤 1–3；只要阶段 → 必须先有 holders。

## 配方 B · 发现

用已有 meme-rush / gmgn trenches 拉候选（不要新爬虫）→ 对每个地址跑 safety → 失败者进不碰名单 → 幸存者跑 A 的 holders+stage。叙事只对前 3 个。

## 配方 C · 概念扫描

本公开包未收录 `meme-concept`。需要热点扫描时在原项目跑。

## 输出

必须有：红线结论、阶段、循环是否在转、能/不能做的理由。禁止只贴行情数字。
决策只用：淘汰 / 观察 / 小仓试探 / 趋势跟随。

配方结论**不是**下单。本公开包不含自动交易 skill。

## 铁律

1. 先淘汰再叙事
2. 先定阶段再读数
3. 仓位即观点
