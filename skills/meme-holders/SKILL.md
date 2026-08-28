---
name: meme-holders
description: >
  Meme 持币真实用户分析统一入口。把 holder_count 里的机器人/女巫/bundler/洗盘剥掉，估算有多少真人、真人握多少筹码；SOL 额外给出 bundler 行为分型（快进快出/缓慢派发/持仓待发/高位回补）。
  用户说持仓分析、holder、真实用户、有多少真人、筹码分布、bundler、女巫、pump.fun 筹码、丢合约地址要看人机结构时使用本 skill。
  不要用链名去选 sol-holder-analysis / bsc-holder-analysis / robinhood-holder-analysis，那些是本 skill 内部脚本。
---
# meme-holders

> 回答框架第三节：**筹码干不干净？有多少真人？bundler 在加仓还是在派发？**
> 脚本不重写，按链分发到已有实现。信封字段见 `skills/_shared/envelope.md`。

## 何时调用

- 单币研判里 safety 通过之后（或用户只要看筹码）
- 用户直接丢合约地址并问持仓 / 真人 / bundler

不要在这里讲叙事、定阶段。输出 JSON 后交给 `meme-stage`。

## 怎么跑

```bash
cd skills

# 自动认链：0x → bsc，其余 → sol。pump.fun 的 0x 必须显式 robinhood
python3 meme-holders/dispatch.py --address <ADDR>

python3 meme-holders/dispatch.py --chain sol --address Ai66LHZG9MCzg1WKdawwqduVAXpNDUuV8M3uyq5ppump
python3 meme-holders/dispatch.py --chain bsc --address 0x4400eea4759d6c0274d71d3bec66d21e9c7c7777
python3 meme-holders/dispatch.py --chain robinhood --address 0xfe242d1da8fd04f6a1f80b6d3d807b02e062ad4e
```

脚本会打印中文报告，并把原始 JSON 写到对应 skill 的 `data/`。再收进信封：

```bash
python3 _shared/merge_envelope.py \
  --holders-raw <刚才打印的详细结果路径> \
  --out _shared/runs/envelope.json
```

## 怎么读（阈值来自框架，不要另编）

- 真实用户占比 < 30%：社区是演的
- > 60%：持有人结构健康
- **真人持筹码比例比人数更重要**
- SOL bundler：看分型，不看数量。快进快出过半偏空；回补多或卖出进度 <50% 偏多；未实现/流动性 >1x 是走不掉的抛压

## 分发规则

| 链 | 实际脚本 |
|----|----------|
| sol | `sol-holder-analysis/analyze_sol_holders.py` |
| bsc | `bsc-holder-analysis/analyze_bsc_holders.py` |
| robinhood | `robinhood-holder-analysis/analyze_robinhood_holders.py` |
| 其他 | `holder-analysis/analyze_holders.py --chain <链>` |

`0x` 默认仍是 BSC。用户说 Robinhood / 罗宾汉链，或 pump.fun 链接带着 `0x` 合约时，必须 `--chain robinhood`。

## 依赖

`gmgn-cli` 密钥读仓库根或 `skills/.env` 的 `GMGN_API_KEY`（见 `.env.example`）。

## 铁律

先淘汰再叙事；本块只提供筹码证据，结论里的阶段必须等 `meme-stage`。
