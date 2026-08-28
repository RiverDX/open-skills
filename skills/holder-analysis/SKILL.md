---
name: holder-analysis
description: >
  通用链 holder 脚本实现（base 等）。不要作为默认入口。
  用户要看持仓/真人时用 meme-holders。
---

# holder-analysis - 持币真实用户分析

> **一句话**：holder_count 是镜花水月，真实用户数才是共识的地基。

## 这个 skill 解决什么

GMGN 页面上的"持有人数"从来不等于真实用户数。一个显示 200 持有人的币，里面可能有：

| 水分来源 | 典型手法 | 数据特征 |
|---|---|---|
| LP池/销毁地址 | 正常存在但非用户 | `addr_type==2` / 有 `exchange` 字段 |
| 捆绑钱包(bundler) | 一次性批量创建几十个钱包买入 | 零卖出、同步建仓、`transfer_in` 进账 |
| 女巫/fresh wallet | 批量小号凑持有人数 | `fresh_wallet` 标签 / `is_new=true` |
| 洗盘机器人 | 自买自卖刷量 | `wash_trader` 标签、成交量/流动性比畸高 |
| 狙击机器人 | 开盘自动抢筹 | `sniper` 标签 |
| 灰尘地址 | 空投 0.0001 个币凑数 | `usd_value` 趋近 0 |

本 skill 回答的问题：**这个币背后到底有多少真人？** 这是 meme-scout 五维判断里"共识沉淀"维度的定量依据，也是判断"拉盘有没有真实接盘者"的核心指标。

## 分析逻辑（层层剥洋葱）

对 top 持仓逐个地址判定，命中剔除规则即归类（按序短路）：

```
holder_count (官方数字)
  ├─ 剔除 LP池/销毁        ← addr_type==2 或有 exchange
  ├─ 剔除 可疑地址          ← is_suspicious
  ├─ 剔除 洗盘              ← tags 含 wash_trader
  ├─ 剔除 狙击机器人        ← tags/maker_token_tags 含 sniper
  ├─ 剔除 新钱包(女巫)      ← fresh_wallet 标签 或 is_new
  ├─ 剔除 纯转入(捆绑/空投) ← buy_tx==0 且 transfer_in>0
  ├─ 剔除 灰尘地址          ← usd_value < $1 (可调)
  └─ 剩余 = 疑似真实用户
```

**尾部外推**：holders 接口最多取 100 个，若 holder_count > 100，按 top100 中"非池地址的真实占比"外推全体真实用户数。

**质量信号**（真实用户里的加分项，判断"真人成色"）：
`gmgn` 标签（在用 GMGN 工具的真人）、`fomo`（散户追高行为）、twitter 绑定、加仓行为（买入≥2笔）、native_balance>0（钱包里有 gas 费）。

**全链交叉验证**（token info 的 stat 字段，注意其统计口径与持仓列表不完全一致，仅作旁证）：
- `fresh_wallet_rate` / `wallet_tags_stat.fresh_wallets`：新钱包占比
- `bot_degen_rate`：机器人交易占比
- `vol24 / liquidity`（换手倍数）：>5x 有洗盘嫌疑
- `creator_created_count`：>20 是批量发币工作室
- `image_dup_count`：同图撞车币数量

## 标准工作流

```
python3 skills/holder-analysis/analyze_holders.py --chain bsc --address 0x...
  # 输出中文报告 + data/holder-analysis/holder_analysis_*.json
  # 需要更严格的灰尘过滤时: --dust 5
  # 已有 raw 数据时: --info info.json --holders holders.json
```

结果怎么读：

- **真实用户占比 < 30%**：筹码基本在机器人和团伙手里，"社区"是演出来的 → 共识沉淀极弱
- **30%–60%**：有水分但有基本盘，需结合质量信号看
- **> 60%**：持有人结构健康，共识有真实地基
- **真实用户持有筹码占比**比"人数占比"更重要——10 个真人 hold 5% 筹码好过 100 个机器人 hold 60%
- **换手倍数畸高 + 真实用户少** = 典型刷量盘，成交量数据不可信

## 与其他 skill 的衔接

- 上游：`meme-scout` 叙事分高、`market_opportunity.py` 技术分不低时，用本 skill 深挖"共识沉淀"维度
- 数据源同 `gmgn-cli token info/holders`，无需额外配置
- 输出 JSON 落盘 `data/holder-analysis/`，可回溯对比持有人结构变化（同一币隔几天再跑一次）

## 注意

- GMGN 的 `wallet_tags_stat` 与持仓列表逐个统计的口径不一致（前者疑似含已离场交易者），以持仓列表逐个判定为准，前者仅作旁证
- "疑似真实用户"仍是估算：一个用惯了的老钱包也可能属于团伙；反之 fresh wallet 偶尔也是真新人的第一个钱包
- 所有分析**仅供参考，不构成投资建议**，务必 DYOR
