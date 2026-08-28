#!/usr/bin/env python3
"""红线闸门：能判定的就判定，查不到的列入 unchecked，不假装过关。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 允许从 holder 原始 JSON 直接跑
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '_shared'))
from merge_envelope import from_holders_raw  # noqa: E402


def pick(info: dict, *keys):
    for k in keys:
        if info.get(k) is not None:
            return info.get(k)
    return None


def evaluate(holders_raw: dict | None, info: dict | None) -> dict:
    fails, warnings, unchecked = [], [], []
    token = {}
    top10 = None
    wash = False
    creator_n = None

    if holders_raw:
        mapped = from_holders_raw(holders_raw)
        token = mapped.get('token') or {}
        h = mapped.get('holders') or {}
        conc = holders_raw.get('concentration') or {}
        gmgn_top10 = conc.get('gmgn_top10_rate')
        try:
            top10 = float(gmgn_top10) if gmgn_top10 is not None else h.get('top10_pct')
        except (TypeError, ValueError):
            top10 = h.get('top10_pct')
        creator_n = h.get('creator_created_count')
        cats = holders_raw.get('classification') or {}
        wash_n = cats.get('wash_trader') or 0
        if wash_n:
            if wash_n >= 5:
                wash = True
            else:
                warnings.append(f'持仓样本中 {wash_n} 个 wash_trader（未达红线）')
        churn = h.get('churn')
        if churn is not None and churn > 5:
            warnings.append(f'换手 {churn}x，洗盘嫌疑（未当红线淘汰）')
        avg_tx = h.get('avg_tx_per_holder')
        if avg_tx is not None and avg_tx > 8:
            warnings.append(f'人均成交 {avg_tx} 笔/holder（>8 小单刷屏，未当红线）')
        spm = h.get('swaps_per_min_1h')
        if spm is not None and spm > 80:
            warnings.append(f'近1h {spm} 笔/分钟（过热，未当红线）')

    info = info or {}
    if info:
        token.setdefault('symbol', info.get('symbol'))
        token.setdefault('name', info.get('name'))
        token.setdefault('address', info.get('address'))
        token.setdefault('chain', info.get('chain') or info.get('chainId'))

    # Top10
    if top10 is None:
        unchecked.append('Top10 持仓占比')
    else:
        pct = top10 * 100 if top10 <= 1 else top10
        if pct > 30:
            fails.append(f'Top10 持仓 {pct:.1f}% > 30%')

    if holders_raw is None:
        unchecked.append('洗盘地址逐个判定')
    elif wash:
        fails.append('持仓中出现 wash_trader')

    # 合约权限：有字段才判，没有就 unchecked
    honeypot = pick(info, 'is_honeypot', 'honeypot', 'isHoneypot')
    freeze = pick(info, 'freeze_authority', 'is_frozen', 'cannot_sell')
    if honeypot is None and freeze is None and 'renounced_mint' not in info and 'mint_authority' not in info:
        unchecked.append('合约增发/冻结/蜜罐（未跑 token security）')
    else:
        if honeypot in (True, 1, '1', 'true'):
            fails.append('蜜罐')
        if freeze in (True, 1, '1', 'true'):
            fails.append('可冻结或无法卖出')
        if info.get('renounced_mint') is False:
            fails.append('mint 未 renounce')

    creator_close = pick(info, 'creator_close')
    if creator_n is not None and creator_n > 20:
        warnings.append(f'创建者历史发币 {creator_n}，工作室量产（案例中不当红线）')
    if creator_close is False:
        warnings.append('创建者未清仓，对照框架核对 dev 持仓是否 >5%')

    return {
        'token': {k: v for k, v in token.items() if v is not None},
        'safety': {
            'pass': len(fails) == 0,
            'fails': fails,
            'warnings': warnings,
            'unchecked': unchecked,
        },
    }


def main():
    ap = argparse.ArgumentParser(description='meme-safety 红线闸门')
    ap.add_argument('--holders-raw', help='holder 脚本原始 JSON')
    ap.add_argument('--info', help='gmgn token info raw JSON（可选，补合约权限）')
    ap.add_argument('--out', help='写出 JSON')
    args = ap.parse_args()
    if not args.holders_raw and not args.info:
        ap.error('至少提供 --holders-raw 或 --info')

    holders_raw = json.loads(Path(args.holders_raw).read_text()) if args.holders_raw else None
    info = json.loads(Path(args.info).read_text()) if args.info else None
    result = evaluate(holders_raw, info)

    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    s = result['safety']
    print('\n===== 红线 =====', file=sys.stderr)
    print('通过' if s['pass'] else '淘汰: ' + '; '.join(s['fails']), file=sys.stderr)
    if s['warnings']:
        print('警示: ' + '; '.join(s['warnings']), file=sys.stderr)
    if s['unchecked']:
        print('未检查: ' + '; '.join(s['unchecked']), file=sys.stderr)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + '\n')


if __name__ == '__main__':
    main()
