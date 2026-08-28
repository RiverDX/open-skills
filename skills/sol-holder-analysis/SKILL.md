---
name: sol-holder-analysis
description: >
  Solana holder 分析脚本实现（bundler 分型）。不要作为默认入口。
  用户要看持仓/真人/bundler 时用 meme-holders；仅当明确要求直接跑 analyze_sol_holders.py 时才用本 skill。
---

# sol-holder-analysis - SOL 持币真实用户分析

> **一句话**：holder_count 是镜花水月，真实用户数才是共识的地基。

## 这个 skill 解决什么

GMGN 页面上的"持有人数"从来不等于真实用户数。一个显示 9 万持有人的 pump.fun 币，top 持仓里可能 7 成是捆绑机器人。水分来源：

| 水分来源 | 典型手法 | 数据特征 |
|---|---|---|
| LP池 | pump_amm / meteora 池子 | `addr_type==2` / 有 `exchange` 字段 |
| **捆绑机器人(bundler)** | 同一区块打包几十个钱包狙击开盘 | `maker_token_tags` 含 `bundler`，买入几十~几百笔、收益畸高 |
| 三明治机器人 | 夹子攻击获利 | `tags` 含 `sandwich_bot` |
| 女巫/fresh wallet | 批量小号 | `fresh_wallet` 标签 / `is_new=true` |
| 洗盘机器人 | 自买自卖刷量 | `wash_trader` 标签、成交量/流动性比畸高 |
| 纯转入地址 | 内部分发/空投 | `buy_tx==0` 且 `transfer_in>0` |
| 灰尘地址 | 空投碎币凑数 | `usd_value` 趋近 0 |

## SOL 与 BSC 的关键差异（实测 pump.fun 代币得出）

1. **`bundler` 是 SOL 最强的机器人信号**：BSC 数据里没有，SOL 的 `maker_token_tags` 直接标注。实测 CATE top100 里 69% 是 bundler
2. **`sandwich_bot` 三明治机器人标签**：SOL 特有
3. **transfer_in 不能单独当信号**：pump.fun bonding curve 机制下正常买入也伴随 transfer_in，"纯转入"判定必须同时要求 `buy_tx==0`
4. **`axiom`/`padre`/`gmgn` 等 tags 是交易工具用户**：真人用 App 交易的质量信号
5. **大盘子不能按 top100 外推**：9 万持有人的币，top100 只覆盖 37% 筹码且全是鲸鱼/机器人，按 top100 比例外推会严重失真

## 分析逻辑（层层剥洋葱）

对 top 持仓逐个地址判定，命中剔除规则即归类（按序短路）：

```
holder_count (官方数字)
  ├─ 剔除 LP池             ← addr_type==2 / 有 exchange
  ├─ 剔除 可疑地址          ← is_suspicious
  ├─ 剔除 洗盘              ← tags 含 wash_trader
  ├─ 剔除 三明治机器人      ← tags 含 sandwich_bot (SOL特有)
  ├─ 剔除 牵击机器人        ← tags/maker_token_tags 含 sniper
  ├─ 剔除 捆绑机器人        ← maker_token_tags 含 bundler (SOL特有)
  ├─ 剔除 新钱包(女巫)      ← fresh_wallet 标签 或 is_new
  ├─ 剔除 纯转入(分发/空投) ← buy_tx==0 且 transfer_in>0
  ├─ 剔除 灰尘地址          ← usd_value < $1 (可调)
  └─ 剩余 = 疑似真实用户
```

**真实用户估算分两种模式（自动按筹码覆盖率切换）**：

- **覆盖率 >= 90%（小盘子）**：按 top100 真实占比外推全体（同 BSC 逻辑）
- **覆盖率 < 90%（大盘子/鲸鱼结构）**：top100 只代表鲸鱼筹码结构，单独展示；
  全体真实用户 = `holder_count × (1-bot_degen_rate) × (1-fresh_wallet_rate)` 估算，两套数字并列注明口径

**质量信号**（真实用户里的加分项，判断"真人成色"）：
交易工具用户（`gmgn`/`axiom`/`padre`/`photon`/`bullx`）、`fomo`（散户追高）、`bluechip_owner`（蓝筹持有者）、twitter 绑定、加仓行为（买入≥2笔）、native_balance>0（钱包里有 SOL 付 gas）。

**全链交叉验证**（token info 的 stat 字段，统计口径与持仓列表不完全一致，仅作旁证）：
- `top_bundler_trader_percentage`：捆绑交易者占比（SOL 特有，>50% 极脏）
- `top_entrapment_trader_percentage`：套牢盘交易者占比
- `fresh_wallet_rate` / `bot_degen_rate`：全体估算的输入
- `vol24 / liquidity`（换手倍数）：>5x 有洗盘嫌疑
- `avg_tx_per_holder`（24h买卖笔数/holder）：>8 小单刷屏，>12 偏对倒。和换手互补：同样 8x 换手，Sheep 人均 4、XYZ 人均 9
- `swaps_per_min_1h`（近1h笔数/分钟）：当下密不密；>30 热盘，>80 过热。不要用 24h 笔数除以 1440 代替——会把这一小时烫盘稀释掉
- `creator_created_count`：>20 是批量发币工作室（pump.fun 上万级 = 纯量产号）

## bundler 行为分型（"bundler 也有价值"的正确打开方式）

有人说捆绑机器人也有价值--**条件成立，关键看 bundler 在干什么，而不是有多少个**。
脚本对 top 持仓里的 bundler 逐个做行为分型：

| 分型 | 判定 | 含义 |
|---|---|---|
| 快进快出 | 卖出进度>=80% | 纯狙击者，利润已兑现、筹码已派发完，**利空落地** |
| 缓慢派发 | 卖出进度 20-80% | 正在出货，**每次上涨都会被卖给** |
| 持仓待发 | 卖出进度<20% 且已实现收益>=0 | 拿着百万级浮盈不卖，等更大行情 |
| 高位回补 | 已实现收益<0（回补被套仍持有） | 在更高价位重新买入，**最强的看多信号** |

配套的整体指标：

- **兑现率** = 已实现/(已实现+未实现)：低兑现率 = bundler 不急着走
- **净流入**：正 = 整体还在净加仓
- **未实现利润/流动性**：>1x 说明浮盈根本无法一次性退出（部分"持有"是被锁住的浮盈，也压制每次拉升）
- **读法**：`回补数>=5 或 卖出进度<50%` 偏看多；`快进快出过半` 偏看空；否则中性偏空（缓慢派发）

> 注意陷阱：bundler 大额未实现利润是**延迟的抛压**，不等于承诺持有。"未实现/流动性 = 4.5x"时，
> 它们想走也走不掉，只能等流动性/成交量涨起来慢慢出--所以这个"看多"信号要配合成交量趋势验证。

## 标准工作流

```
python3 sol-holder-analysis/analyze_sol_holders.py --address Ai66LHZG9MCzg1WKdawwqduVAXpNDUuV8M3uyq5ppump
  # 输出中文报告 + sol-holder-analysis/data/holder_analysis_*.json
  # 需要更严格的灰尘过滤时: --dust 5
  # 已有 raw 数据时: --info info.json --holders holders.json
```

结果怎么读：

- **top 持仓真实占比**：反映"筹码在谁手里"。pump.fun 新币常见 bundler 占 60%+，即筹码大部分在狙击团伙手里
- **全体真实用户估算**：反映"社区规模"。大盘子看这个，小盘子两者一致
- **真实用户持有筹码占比**比人数更重要--鲸鱼机器人的 37% 筹码 vs 真人的 4.5% 筹码，说明拉盘容易但没人接盘
- **换手倍数畸高 + bundler 高占比** = 典型刷量盘，成交量数据不可信

## 实测参考（Catecoin/CATE, 2026-08）

pump.fun 发射，90,568 持有人，$178 万流动性，$28M 日成交量。top100（覆盖 36.9% 筹码）里：
**69% 是捆绑机器人、14% 真实用户**（真人只持有 4.5% 筹码）。全链旁证：捆绑交易者 54%、
套牢盘 51%、机器人率 40%、换手 15.7x、创建者历史发币 19,355 个（量产号）。
全体估算 ~5 万真实用户--表面 9 万人的社区，刨掉机器人和女巫后缩水近半，
且真正 hold 筹码的真人占比极低，筹码高度机器化。

但 bundler 行为分型给出了另一面：69 个 bundler 仅兑现 19% 利润（已实现 $186 万 vs
未实现 $805 万），卖出进度 45%，净流入 +$347 万，11 个高位回补被套仍持有，25 个浮盈
不卖。分型结论偏看多：**机器人在净加仓而非派发**--"bundler 也有价值"在这个案例上
成立，但未实现利润/流动性 = 4.5x，兑现通道本身受限，需配合成交量趋势验证。

## 注意

- GMGN 的 `wallet_tags_stat` 有封顶（实测 bundler/fresh 都恰好 = 1000），是"top N"统计不是全量，全体估算用 `stat` 里的 rate 字段
- 大盘子模式的全体估算是粗估：bot/fresh rate 的统计母体疑似是交易者而非持有人，实际真实持有人可能偏高或偏低，量级参考即可
- "疑似真实用户"仍是估算：老钱包也可能属于团伙；bundler 偶尔也是真人用批量工具
- 所有分析**仅供参考，不构成投资建议**，务必 DYOR
