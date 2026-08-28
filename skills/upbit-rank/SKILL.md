---
name: upbit-rank
description: >
  查询 Upbit（업비트）韩国站 24 小时成交额榜和涨幅榜前 10。使用官方公开行情 API，无需 API Key。
  用户提到 Upbit、업비트、韩国交易所、KRW 市场、Upbit 成交量、成交额榜、涨幅榜、热门币、今日涨幅、volume leaderboard、gainers 时使用本 skill。
---
# Upbit 成交额 / 涨幅榜

用官方公开行情一次拉全市场，排出 **24h 成交额 Top 10** 和 **涨幅 Top 10**。不要手写 curl 再自己排序，直接跑捆绑脚本。

## 何时用

- 「Upbit 成交量 / 成交额榜」
- 「Upbit 涨幅榜前 10」
- 「韩国站今天什么币在涨 / 什么最活跃」

默认市场是 **KRW**。用户若指定 BTC / USDT 报价，把 `--quote` 改掉。

## 怎么跑

脚本：本 skill 目录下的 `scripts/rank.py`。

韩国站 `api.upbit.com` 在国内常连不上。按这个顺序处理代理：

1. 当前环境已有 `https_proxy` / `http_proxy` → 直接跑
2. 否则显式加上用户代理，常见是 `http://127.0.0.1:7897`
3. 脚本自己还会回退到 `http://127.0.0.1:7897`，再不行才直连

```bash
python3 "<skill_dir>/scripts/rank.py" --quote KRW --top 10
# 需要时：
python3 "<skill_dir>/scripts/rank.py" --proxy http://127.0.0.1:7897
python3 "<skill_dir>/scripts/rank.py" --format json
```

把 `<skill_dir>` 换成本 skill 的实际路径。

## 口径

| 榜单 | 排序字段 | 含义 |
|------|----------|------|
| 成交额榜 | `acc_trade_price_24h` | 滚动 24 小时成交额（报价货币，KRW 市场即韩元） |
| 涨幅榜 | `signed_change_rate` | 相对 **前一日 UTC 收盘价**，与 Upbit 行情页一致，不是滚动 24h 涨跌 |

涨幅榜会带上 24h 成交额，方便判断是真放量还是流动性很差的拉涨。`market_warning != NONE` 的交易对在表里标 ⚠。

## 回复格式

用中文直接给出两张表，不要先问要不要保存笔记。结构：

1. 一句话摘要（哪几个币成交额最大、谁领涨）
2. 24h 成交额 Top 10
3. 涨幅榜 Top 10
4. 需要时补一句口径：涨跌看的是昨日收盘，不是滚动 24h

表格列：排名、交易对、名称、现价、涨跌、24h 成交额、24h 成交量。

用户没要求落库时，不要写日记或项目笔记。

## 不要做的事

- 不要用币安 Web3 / CoinGecko 顶替 Upbit 官方数据
- 不要调用需要 API Key 的 Exchange 接口（下单、资产）
- 不要把涨幅理解成滚动 24 小时收益率
