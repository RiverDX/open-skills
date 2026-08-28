---
type: reference
project: open-skills
---
# 共享信封

所有原子 Skill 往同一份 JSON 里写自己的键。没跑过的键保持缺失，禁止填 0 假装跑过。
编排器 `meme-workflow` 只合并这份对象。

路径约定：单币一次分析写到 `skills/_shared/runs/<symbol>_<addr10>_<ts>.json`。

```json
{
  "token": {
    "chain": "sol",
    "address": "",
    "symbol": "",
    "name": ""
  },
  "safety": {
    "pass": true,
    "fails": [],
    "warnings": [],
    "unchecked": []
  },
  "holders": {
    "official_count": 0,
    "real_user_pct": 0,
    "real_user_supply_pct": 0,
    "top10_pct": 0,
    "bundler": {
      "count": 0,
      "sell_progress": 0,
      "realization_ratio": 0,
      "netflow_usd": 0,
      "verdict": ""
    },
    "source": ""
  },
  "flow": {
    "mcap": null,
    "vol_mcap": null,
    "net_inflow": null,
    "liq_mcap": null,
    "churn": null,
    "sync": "unknown"
  },
  "smart_money": {
    "bias": "none"
  },
  "narrative": {
    "score": null,
    "qualitative": ""
  },
  "stage": {
    "name": "",
    "confidence": "low",
    "why": ""
  },
  "environment": {
    "window": "unknown"
  },
  "decision": {
    "action": "",
    "one_liner": ""
  }
}
```

`safety.pass === false` 时配方短路，后面的键可以不填。
`meme-stage` 若缺 `holders` 与 `flow` 两者之一，必须把 `confidence` 设为 `low`。
