"""从本项目目录加载 .env，不再读取仓库外的路径。

已在进程环境里的键优先；文件只补缺（含 GMGN_PRIVATE_KEY、AUTO_TRADE_*）。
查找顺序：当前工作目录 `.env` → `skills/.env` → 项目根 `.env`。
"""
from __future__ import annotations

import os
from pathlib import Path

# skills/_shared/env.py → 仓库根 open-skills/
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = Path(__file__).resolve().parents[1]


def _apply_dotenv(env: dict, path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, _, v = line.partition('=')
        env.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def cli_env() -> dict:
    env = os.environ.copy()
    for p in (Path.cwd() / '.env', SKILLS_DIR / '.env', PROJECT_ROOT / '.env'):
        _apply_dotenv(env, p)
    return env
