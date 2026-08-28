---
name: meme-stage
description: >
  Meme 生命周期阶段判断。只读共享信封（holders/flow），不拉链上数据。
  输出冷启动 / 故事期 / 共识期 / 博傻期。用户说现在什么阶段、还能不能追、是不是最后一棒、生命周期时使用。
  同一组数字在不同阶段含义相反，所以必须在写结论之前调用。
---
# meme-stage

> **我在循环的哪一段？** 先定阶段再读数。
> 本 skill **禁止**调用 gmgn-cli / API。缺字段就 `confidence=low`，不要硬判。

## 规则（不要另编阈值）

| 阶段 | 主要特征 |
|------|----------|
| 冷启动 | holder < 500，量小，故事未验证 |
| 故事期 | 涨幅约 50%–500%，holder 增速、聪明钱进场、量价同步 |
| 共识期 | 涨幅约 5–20 倍，holder > 1 万 |
| 博傻期 | 涨幅 > 20 倍，或大户/bundler 已大幅派发，量增价滞 |

## 怎么跑

先有信封（至少含 `holders`）：

```bash
python3 skills/meme-stage/judge_stage.py \
  --envelope skills/_shared/runs/envelope.json \
  --out skills/_shared/runs/stage.json

python3 skills/_shared/merge_envelope.py \
  --envelope skills/_shared/runs/envelope.json \
  --stage skills/_shared/runs/stage.json \
  --out skills/_shared/runs/envelope.json
```

## 读数纪律

先定阶段再读数。例如真人少在冷启动是赌博，在共识期是「拉盘没人接」。
Catecoin 案例：holder 很大但真人筹码极少，阶段偏共识、并注明往博傻滑。
