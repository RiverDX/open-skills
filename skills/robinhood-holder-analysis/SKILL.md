---
name: robinhood-holder-analysis
description: >
  Robinhood Chain holder 分析脚本实现。GMGN 链名是 robinhood，合约是 0x，Gas 是 ETH。
  用户丢 pump.fun 的 0x 地址、说 Robinhood / 罗宾汉链 / hood 链持仓时，经 meme-holders --chain robinhood 进来。
  不要把 0x 默认当成 BSC。仅当明确要求直接跑 analyze_robinhood_holders.py 时才跳过分发入口。
---
# robinhood-holder-analysis - Robinhood 持币真实用户分析

> **一句话**：pump.fun 上的 `0x` 合约经常在 Robinhood Chain，不是 BSC。链名必须显式传 `robinhood`。

## 这个 skill 解决什么

Robinhood 是 EVM L2，地址长得和 BSC/Base/ETH 一样（`0x` + 40 hex）。GMGN 网页、App、API、`gmgn-cli` 都已支持，slug 是 **`robinhood`**。

本仓库旧逻辑把所有 `0x` 判成 BSC，所以会拉出 holder=0、流动性=$0 的空结果。本 skill 把取数链钉死在 `robinhood`。

Launchpad 常见：Pump.fun、Flap、Flapstock、Klik、Noxa、Trench、Pons。Gas 代币是 **ETH**，不是 BNB。

网页：`https://gmgn.ai/robinhood/token/<ADDRESS>`

## 分析逻辑（与 BSC 相同，层层剥洋葱）

```
holder_count (官方数字)
  ├─ 剔除 LP池/销毁        ← addr_type==2 / 有 exchange / 黑洞地址
  ├─ 剔除 可疑地址          ← is_suspicious
  ├─ 剔除 洗盘              ← tags 含 wash_trader
  ├─ 剔除 狙击机器人        ← tags/maker_token_tags 含 sniper
  ├─ 剔除 新钱包(女巫)      ← fresh_wallet 标签 或 is_new
  ├─ 剔除 纯转入(捆绑/空投) ← buy_tx==0 且 transfer_in>0
  ├─ 剔除 灰尘地址          ← usd_value < $1 (可调)
  └─ 剩余 = 疑似真实用户
```

**尾部外推**：holders 最多取 100；holder_count > 100 时按 top 中非池真实占比外推。

**质量信号**：`gmgn` / `fomo` / twitter / 加仓≥2 笔 / `native_balance>0`（这里是 ETH）。

**盘口旁证**（不当单独红线）：
- 换手 `vol24/流动性` >5x → 洗盘嫌疑
- 人均成交 `(24h买+卖)/holder` >8 小单刷屏，>12 偏对倒
- 近 1h 笔数/分钟 >30 热盘，>80 过热

## 怎么跑

默认走统一入口（推荐）：

```bash
cd skills
python3 meme-holders/dispatch.py --chain robinhood --address 0xfe242d1da8fd04f6a1f80b6d3d807b02e062ad4e
```

直接跑本脚本：

```bash
python3 robinhood-holder-analysis/analyze_robinhood_holders.py --address 0xfe242d1da8fd04f6a1f80b6d3d807b02e062ad4e
```

CLI 等价取数：

```bash
gmgn-cli token info    --chain robinhood --address <ADDR> --raw
gmgn-cli token holders --chain robinhood --address <ADDR> --limit 100 --raw
```

结果写 `robinhood-holder-analysis/data/holder_analysis_*.json`。

本机 `gmgn-cli` 1.1.x 会拒认 `robinhood`。脚本会改用已安装 CLI 的 OpenAPI 客户端（`fetch_via_installed_cli.mjs`）。升到 1.5+ 后才走 CLI 命令本身。

## 怎么读

- 真实用户人数占比 <30%：社区是演的
- >60%：持有人结构健康
- **真人持筹码比例比人数更重要**
- Top10 >30% = 红线淘汰（交给 `meme-safety`）
- 砸盘库目前主要是 SOL 地址；Robinhood 的 `0x` 交叉大概率空，空不等于干净

## 认链铁律

| 信号 | 链 |
|------|----|
| 用户说 Robinhood / hood / 罗宾汉链 | `robinhood` |
| pump.fun 链接 + `0x` 合约 | 先 `robinhood`，BSC 拉空再确认 |
| 用户明确说 BSC / FourMeme | `bsc` |
| 非 `0x` 地址 | `sol` |

`0x` 在本仓库默认仍是 BSC。Robinhood 币必须带 `--chain robinhood`。

## 依赖

本机 `gmgn-cli` 1.1.x 会拒认 `robinhood`。脚本会自动改走 `https://openapi.gmgn.ai`。升级到 1.5+ 后才走 CLI。
