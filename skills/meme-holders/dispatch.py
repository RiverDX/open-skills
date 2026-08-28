#!/usr/bin/env python3
"""按链分发到已有 holder 脚本，不重复实现分析逻辑。"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def infer_chain(address: str | None, chain: str | None) -> str:
    if chain:
        c = chain.lower().strip()
        aliases = {
            'solana': 'sol',
            'bnb': 'bsc',
            'rh': 'robinhood',
            'hood': 'robinhood',
            'robinhood-chain': 'robinhood',
        }
        return aliases.get(c, c)
    a = (address or '').strip()
    if a.startswith('0x') and len(a) == 42:
        return 'bsc'
    return 'sol'


def script_for(chain: str) -> tuple[Path, list[str]]:
    if chain in ('sol', 'solana'):
        return ROOT / 'sol-holder-analysis' / 'analyze_sol_holders.py', []
    if chain in ('bsc', 'bnb'):
        return ROOT / 'bsc-holder-analysis' / 'analyze_bsc_holders.py', []
    if chain in ('robinhood', 'rh', 'hood'):
        return ROOT / 'robinhood-holder-analysis' / 'analyze_robinhood_holders.py', []
    # base / eth / arc / stable 等：通用脚本
    return ROOT / 'holder-analysis' / 'analyze_holders.py', ['--chain', chain]


def main():
    ap = argparse.ArgumentParser(description='meme-holders 分发入口')
    ap.add_argument('--chain', help='sol / bsc / robinhood / base。省略则 0x=bsc，其余=sol。pump.fun 的 0x 用 robinhood')
    ap.add_argument('--address')
    ap.add_argument('--info')
    ap.add_argument('--holders')
    ap.add_argument('--dust', default=None)
    args, extra = ap.parse_known_args()

    chain = infer_chain(args.address, args.chain)
    script, prefix = script_for(chain)
    if not script.exists():
        sys.exit(f'找不到脚本: {script}')

    cmd = [sys.executable, str(script), *prefix]
    if args.address:
        cmd += ['--address', args.address]
    if args.info:
        cmd += ['--info', args.info]
    if args.holders:
        cmd += ['--holders', args.holders]
    if args.dust is not None:
        cmd += ['--dust', str(args.dust)]
    cmd += extra
    raise SystemExit(subprocess.call(cmd))


if __name__ == '__main__':
    main()
