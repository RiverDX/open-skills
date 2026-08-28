#!/usr/bin/env python3
"""阶段判断：只读信封，不拉链。缺 holders/flow 则 confidence=low。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def judge(env: dict) -> dict:
    h = env.get('holders') or {}
    flow = env.get('flow') or {}
    missing = []
    if not h:
        missing.append('holders')
    if not flow:
        missing.append('flow')

    official = h.get('official_count')
    real_supply = h.get('real_user_supply_pct')
    top10 = h.get('top10_pct')
    churn = h.get('churn') if h.get('churn') is not None else flow.get('churn')
    bb = h.get('bundler') or {}
    sell = bb.get('sell_progress')
    netflow = bb.get('netflow_usd')
    sync = flow.get('sync')
    gain = flow.get('gain_multiple')  # 现价/成本或相对开盘，可缺

    why = []
    name = None

    # 出货/刷量优先于「人少=冷启动」。张雪机车 holder 199 但是工作室出货，不是冷启动。
    if sell is not None and sell >= 0.8:
        name = '博傻期'
        why.append(f'bundler 卖出进度 {sell:.0%}，快进快出')
    elif churn is not None and churn > 10 and official is not None and official < 10000:
        name = '博傻期'
        why.append(f'换手 {churn}x 畸高且 holder {official} 未形成大社区，偏出货/刷量盘')
    elif official is not None and official < 500:
        name = '冷启动'
        why.append(f'官方 holder {official} < 500')
    elif official is not None and official > 10000:
        name = '共识期'
        why.append(f'官方 holder {official} > 1 万')
        if churn and churn > 10:
            why.append(f'换手 {churn}x 畸高，往博傻期滑')
            name = '共识期'
        if real_supply is not None and real_supply < 0.1:
            why.append(f'真人只握筹码 {real_supply:.1%}，共识水分大')
    elif gain is not None and 0.5 <= gain <= 5:
        name = '故事期'
        why.append(f'涨幅约 {gain:.1f}x，落在 50%–500% 窗口')
    elif gain is not None and gain > 20:
        name = '博傻期'
        why.append(f'涨幅 {gain:.0f}x > 20 倍')
    elif gain is not None and gain > 5:
        name = '共识期'
        why.append(f'涨幅 {gain:.1f}x')

    if sync == 'stall':
        why.append('量增价滞，派发嫌疑')
        if name in ('共识期', '故事期'):
            name = '博傻期' if name == '共识期' else name

    if name is None:
        name = '未知'
        why.append('现有字段不够套框架第八节，需要补 flow.gain_multiple 或 token 年龄')

    confidence = 'low' if missing or name == '未知' else 'medium'
    if not missing and gain is not None:
        confidence = 'high'
    elif missing == ['flow'] and official is not None:
        confidence = 'medium'
        why.append('缺 flow，阶段主要靠 holder 规模，置信中等')

    return {
        'stage': {
            'name': name,
            'confidence': confidence,
            'why': '；'.join(why),
            'missing': missing,
            'signals': {
                'official_count': official,
                'real_user_supply_pct': real_supply,
                'top10_pct': top10,
                'churn': churn,
                'bundler_sell_progress': sell,
                'bundler_netflow_usd': netflow,
                'sync': sync,
                'gain_multiple': gain,
            },
        }
    }


def main():
    ap = argparse.ArgumentParser(description='meme-stage 只读信封定阶段')
    ap.add_argument('--envelope', required=True)
    ap.add_argument('--out')
    args = ap.parse_args()
    env = json.loads(Path(args.envelope).read_text())
    result = judge(env)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    st = result['stage']
    print(f"\n阶段: {st['name']}  置信: {st['confidence']}\n依据: {st['why']}", file=sys.stderr)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + '\n')


if __name__ == '__main__':
    main()
