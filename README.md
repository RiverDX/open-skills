# open-skills

RiverDX 的 Agent Skills 仓库。可用 `npx skills add RiverDX/open-skills` 安装。

## 当前 Skills

| Skill | 作用 |
|-------|------|
| [upbit-rank](skills/upbit-rank/) | Upbit 韩国站 24h 成交额榜 + 涨幅榜前 10 |
| [meme-holders](skills/meme-holders/) | Meme 持仓真人估算入口（SOL / BSC / Robinhood） |
| [robinhood-holder-analysis](skills/robinhood-holder-analysis/) | Robinhood 链 holder 实现（`0x` 不要默认当 BSC） |
| [sol-holder-analysis](skills/sol-holder-analysis/) | Solana holder + bundler 分型 |
| [bsc-holder-analysis](skills/bsc-holder-analysis/) | BSC holder 实现 |
| [meme-safety](skills/meme-safety/) | Top10 / 洗盘 / 蜜罐红线闸门 |
| [meme-stage](skills/meme-stage/) | 生命周期阶段 |
| [meme-workflow](skills/meme-workflow/) | 单币研判编排 |

默认入口是 `meme-holders`。`0x` 默认 BSC；pump.fun 的 `0x` 或用户说 Robinhood 时必须 `--chain robinhood`。

依赖：`gmgn-cli`、仓库根 `.env` 里的 `GMGN_API_KEY`（见 `.env.example`）。不含自动交易，不含本地跑数 JSON。

```bash
cd skills
python3 meme-holders/dispatch.py --chain robinhood --address 0x79fe86b963255ce884bdcac6388c50a599ba277f
```

## 安装

**Cursor / Claude Code / Codex：**

```bash
npx skills add RiverDX/open-skills
```

**Claude.ai / iPad Claude App：**

1. 把 `skills/upbit-rank/` 打成 zip（根目录要能看到 `SKILL.md`）
2. 电脑打开 claude.ai → Customize → Skills → 上传
3. iPad 用同一账号打开 Claude，说「看下 Upbit 涨幅榜」

国内跑脚本可用：

```bash
python3 skills/upbit-rank/scripts/rank.py --proxy http://127.0.0.1:7897
```
