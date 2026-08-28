#!/usr/bin/env python3
"""把各原子块的 JSON 合并进共享信封。没提供的键保持缺失。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load(path: str | None) -> dict:
    if not path:
        return {}
    return json.loads(Path(path).read_text())


def _as_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def bundler_verdict(bb: dict | None) -> str:
    if not bb:
        return ''
    types = bb.get('types') or {}
    count = bb.get('count') or 0
    sell = bb.get('sell_progress') or 0
    if types.get('re_entered', 0) >= 5 or sell < 0.5:
        return '偏看多'
    if count and types.get('exited_fast', 0) >= count * 0.5:
        return '偏看空'
    return '中性偏空'


def from_holders_raw(raw: dict) -> dict:
    """holder 脚本原始输出 → envelope.holders + token"""
    t = raw.get('token') or {}
    est = raw.get('real_user_estimate') or {}
    conc = raw.get('concentration') or {}
    fl = raw.get('chain_flags') or {}
    sample = raw.get('sample') or {}
    n = sample.get('holders_fetched') or 0
    real_in_top = est.get('in_top_holders') or 0
    bb = raw.get('bundler_behavior')
    holders = {
        'official_count': t.get('holder_count'),
        'real_user_pct': round(real_in_top / n, 4) if n else est.get('real_ratio_of_non_pool'),
        'real_user_supply_pct': est.get('real_supply_pct'),
        'top10_pct': _as_float(conc.get('gmgn_top10_rate')) if conc.get('gmgn_top10_rate') is not None else conc.get('top10_holder_pct'),
        'top10_pct_sample': conc.get('top10_holder_pct'),
        'churn': fl.get('vol24_liquidity_churn'),
        'avg_tx_per_holder': fl.get('avg_tx_per_holder'),
        'swaps_per_min_1h': fl.get('swaps_per_min_1h'),
        'creator_created_count': fl.get('creator_created_count'),
        'source': raw.get('_source') or '',
    }
    if bb:
        holders['bundler'] = {
            'count': bb.get('count'),
            'sell_progress': bb.get('sell_progress'),
            'realization_ratio': bb.get('realization_ratio'),
            'netflow_usd': bb.get('netflow_usd'),
            'unrealized_over_liquidity': bb.get('unrealized_over_liquidity'),
            'types': bb.get('types'),
            'verdict': bundler_verdict(bb),
        }
    token = {
        'chain': t.get('chain'),
        'address': t.get('address'),
        'symbol': t.get('symbol'),
        'name': t.get('name'),
        'liquidity_usd': t.get('liquidity_usd'),
        'launchpad': t.get('launchpad'),
    }
    return {'token': token, 'holders': holders}


def merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in extra.items():
        if k == 'token' and isinstance(v, dict):
            t = dict(out.get('token') or {})
            t.update({kk: vv for kk, vv in v.items() if vv is not None})
            out['token'] = t
        else:
            out[k] = v
    return out


def main():
    ap = argparse.ArgumentParser(description='合并原子块 JSON 为共享信封')
    ap.add_argument('--envelope', help='已有信封，在其上合并')
    ap.add_argument('--holders-raw', help='holder 脚本的原始 JSON')
    ap.add_argument('--safety', help='meme-safety 输出 JSON')
    ap.add_argument('--stage', help='meme-stage 输出 JSON')
    ap.add_argument('--narrative', help='narrative_score 或手工 narrative JSON')
    ap.add_argument('--out', required=True, help='写出路径')
    args = ap.parse_args()

    env = load(args.envelope)
    if args.holders_raw:
        env = merge(env, from_holders_raw(load(args.holders_raw)))
    if args.safety:
        s = load(args.safety)
        env = merge(env, {'safety': s.get('safety', s)})
        if s.get('token'):
            env = merge(env, {'token': s['token']})
    if args.stage:
        st = load(args.stage)
        env = merge(env, {'stage': st.get('stage', st)})
    if args.narrative:
        n = load(args.narrative)
        env = merge(env, {'narrative': n.get('narrative', n)})
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(env, ensure_ascii=False, indent=2))
    json.dump(env, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == '__main__':
    main()
