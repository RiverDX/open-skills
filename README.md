# open-skills

RiverDX 的 Agent Skills 仓库。可用 `npx skills add RiverDX/open-skills` 安装。

## 当前 Skills

| Skill | 作用 |
|-------|------|
| [upbit-rank](skills/upbit-rank/) | Upbit 韩国站 24h 成交额榜 + 涨幅榜前 10 |

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
