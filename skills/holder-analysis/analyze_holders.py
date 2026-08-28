#!/usr/bin/env python3
"""
持币地址真实用户分析 - 从 GMGN 持仓/交易数据里估算"真人"数量

理念：holder_count 不等于真实用户数。一个币显示 200 个持有人，
其中可能包含：流动性池/销毁地址、捆绑钱包(批量转账进来的小号)、
fresh wallet(新创建的女巫钱包)、洗盘机器人、狙击机器人、灰尘地址。
本脚本把这些人机信号逐层剥掉，估算"疑似真实用户"数量。

数据源（gmgn-cli，脚本自动拉取，也可用 --info/--holders/--traders 传本地文件）：
  gmgn-cli token info    --chain <c> --address <a> --raw    # holder_count + 钱包标签统计
  gmgn-cli token holders --chain <c> --address <a> --limit 100 --raw
  gmgn-cli token traders --chain <c> --address <a> --limit 100 --raw

剔除逻辑（按顺序判定，命中即归类，不再往下判）：
  1. pool/burn      addr_type==2 或有 exchange 字段（LP 池/销毁地址）
  2. suspicious     is_suspicious=true
  3. wash_trader    tags 含 wash_trader（洗盘）
  4. sniper         tags/maker_token_tags 含 sniper（狙击机器人）
  5. fresh_wallet   tags 含 fresh_wallet 或 is_new=true（新创建小号，女巫概率高）
  6. transfer_only  buy_tx_count_cur==0 且 transfer_in_count>0（纯转入=捆绑/空投分发）
  7. dust           usd_value < 阈值（默认 $1，--dust 可调）
  其余 = 疑似真实用户

真实用户的"质量信号"（加分项，非剔除项）：
  gmgn 标签（在用 GMGN 的真人）、fomo 标签（散户行为）、twitter 绑定、
  加仓行为（买入>=2笔）、native_balance>0（钱包里有 BNB/SOL 付 gas）

用法：
  python3 analyze_holders.py --chain bsc --address 0x4400...
  python3 analyze_holders.py --chain bsc --address 0x4400... --dust 5
  python3 analyze_holders.py --info info.json --holders holders.json   # 已有 raw 数据时
输出：
  终端打印中文报告；详细结果写 data/holder-analysis/holder_analysis_<chain>_<addr>_<ts>.json
"""

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / 'data'


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / '_shared'))
from env import cli_env  # 读本项目 .env，不再用仓库外路径


def run_cli(args):
    """跑 gmgn-cli，stdout 去掉前置的非 JSON 噪音后解析"""
    p = subprocess.run(['gmgn-cli'] + args, capture_output=True, text=True, env=cli_env())
    out = p.stdout.strip()
    i = out.find('{')
    if i < 0:
        print(f"gmgn-cli {' '.join(args)} 未返回 JSON", file=sys.stderr)
        if p.stderr:
            print(p.stderr.strip()[:500], file=sys.stderr)
        sys.exit(1)
    return json.loads(out[i:])


def load_json_arg(path):
    raw = Path(path).read_text()
    i = raw.find('{')
    return json.loads(raw[i:])


def classify_holder(h, dust_usd):
    """返回 (类别, 原因列表)。命中剔除规则即返回，不再继续判。"""
    tags = set(h.get('tags') or [])
    maker_tags = set(h.get('maker_token_tags') or [])
    reasons = []

    if h.get('addr_type') == 2 or h.get('exchange'):
        return 'pool_burn', ['LP池/合约地址']
    if h.get('is_suspicious'):
        return 'suspicious', ['GMGN标记可疑']
    if 'wash_trader' in tags:
        return 'wash_trader', ['洗盘交易者']
    if 'sniper' in tags or 'sniper' in maker_tags:
        return 'sniper', ['狙击机器人']
    if 'fresh_wallet' in tags or h.get('is_new'):
        return 'fresh_wallet', ['新创建钱包(女巫概率高)']

    buys = h.get('buy_tx_count_cur') or 0
    tin = h.get('transfer_in_count') or 0
    if buys == 0 and (tin > 0 or (h.get('current_transfer_in_amount') or 0) > 0):
        return 'transfer_only', ['零买入纯转入(捆绑/空投)']

    usd = float(h.get('usd_value') or 0)
    if usd < dust_usd:
        return 'dust', [f'持仓价值仅 ${usd:.2f}']

    return 'real_user', []


def quality_signals(h):
    """真实用户的质量信号（加分项）"""
    tags = set(h.get('tags') or [])
    sig = []
    if 'gmgn' in tags:
        sig.append('gmgn用户')
    if 'fomo' in tags:
        sig.append('散户fomo')
    if h.get('twitter_username'):
        sig.append('twitter绑定')
    if (h.get('buy_tx_count_cur') or 0) >= 2:
        sig.append('有加仓行为')
    if float(h.get('native_balance') or 0) > 0:
        sig.append('有gas余额')
    if 'kol' in tags:
        sig.append('KOL')
    return sig


def analyze(info, holders, traders, dust_usd):
    holders_list = holders.get('list') or []
    holder_count = info.get('holder_count') or 0
    stat = info.get('stat') or {}
    wts = info.get('wallet_tags_stat') or {}
    price_info = info.get('price') or {}
    dev = info.get('dev') or {}

    cats = Counter()
    reasons_all = Counter()
    real = []
    for h in holders_list:
        cat, reasons = classify_holder(h, dust_usd)
        cats[cat] += 1
        for r in reasons:
            reasons_all[r] += 1
        if cat == 'real_user':
            real.append({
                'address': h.get('address'),
                'usd_value': h.get('usd_value'),
                'amount_percentage': h.get('amount_percentage'),
                'buy_tx': h.get('buy_tx_count_cur'),
                'profit': h.get('profit'),
                'signals': quality_signals(h),
            })

    n = len(holders_list)
    non_pool = sum(v for k, v in cats.items() if k != 'pool_burn')
    real_ratio = (cats['real_user'] / non_pool) if non_pool else 0.0
    # 尾部外推：holders 接口最多取 100，未覆盖部分按 top100 的真实比例估算
    if holder_count > n:
        tail = holder_count - n
        est_total = cats['real_user'] + round(tail * real_ratio)
    else:
        est_total = cats['real_user']

    top_pct = sum(h.get('amount_percentage') or 0 for h in holders_list)
    top10_pct = sum(h.get('amount_percentage') or 0 for h in holders_list[:10])
    real_pct = sum(r['amount_percentage'] or 0 for r in real)

    vol24 = float(price_info.get('volume_24h') or 0)
    liq = float(info.get('liquidity') or 0)
    churn = round(vol24 / liq, 1) if liq else None

    result = {
        'token': {
            'symbol': info.get('symbol'), 'name': info.get('name'),
            'chain': info.get('chain'), 'address': info.get('address'),
            'holder_count': holder_count, 'liquidity_usd': liq,
            'launchpad': info.get('launchpad'),
        },
        'sample': {'holders_fetched': n, 'supply_coverage': round(top_pct, 4)},
        'classification': dict(cats),
        'exclude_reasons': dict(reasons_all),
        'real_user_estimate': {
            'in_top_holders': cats['real_user'],
            'real_ratio_of_non_pool': round(real_ratio, 4),
            'extrapolated_total': est_total,
            'real_supply_pct': round(real_pct, 4),
        },
        'concentration': {
            'top10_holder_pct': round(top10_pct, 4),
            'gmgn_top10_rate': stat.get('top_10_holder_rate'),
        },
        'chain_flags': {
            'fresh_wallet_rate': stat.get('fresh_wallet_rate'),
            'bot_degen_rate': stat.get('bot_degen_rate'),
            'top70_sniper_hold_rate': stat.get('top70_sniper_hold_rate'),
            'wallet_tags_stat': wts,
            'vol24_liquidity_churn': churn,
            'buys_sells_24h': [price_info.get('buys_24h'), price_info.get('sells_24h')],
            'creator_created_count': dev.get('creator_created_count'),
            'image_dup_count': info.get('image_dup_count'),
        },
        'real_users_detail': sorted(real, key=lambda r: -(r['usd_value'] or 0)),
    }
    return result


def print_report(r):
    t = r['token']
    s = r['sample']
    est = r['real_user_estimate']
    c = r['classification']
    fl = r['chain_flags']

    print(f"\n===== {t['name']} ({t['symbol']}) 持币真实用户分析 =====")
    print(f"官方 holder_count: {t['holder_count']}   流动性: ${t['liquidity_usd']:.0f}   launchpad: {t['launchpad']}")
    print(f"样本: top {s['holders_fetched']} 持仓, 覆盖筹码 {s['supply_coverage']*100:.1f}%")

    print(f"\n-- 持仓分类 (top {s['holders_fetched']}) --")
    label = {
        'pool_burn': 'LP池/销毁', 'suspicious': '可疑地址', 'wash_trader': '洗盘',
        'sniper': '狙击机器人', 'fresh_wallet': '新钱包(女巫)', 'transfer_only': '纯转入(捆绑/空投)',
        'dust': '灰尘地址', 'real_user': '疑似真实用户',
    }
    for k in ('pool_burn', 'suspicious', 'wash_trader', 'sniper', 'fresh_wallet',
              'transfer_only', 'dust', 'real_user'):
        if c.get(k):
            print(f"  {label[k]:<14} {c[k]:>4}  ({c[k]/s['holders_fetched']*100:.0f}%)")

    print(f"\n-- 真实用户估算 --")
    print(f"  top持仓中真实用户: {est['in_top_holders']} 个")
    print(f"  非池地址真实占比: {est['real_ratio_of_non_pool']*100:.1f}%")
    print(f"  全体外推估算:     ~{est['extrapolated_total']} 个真实用户 (官方 holder_count={t['holder_count']})")
    print(f"  真实用户持有筹码: {est['real_supply_pct']*100:.1f}%")

    print(f"\n-- 全链警示信号 --")
    if fl.get('fresh_wallet_rate') is not None:
        print(f"  新钱包比例: {float(fl['fresh_wallet_rate'])*100:.1f}%")
    if fl.get('bot_degen_rate') is not None:
        print(f"  机器人交易比例: {float(fl['bot_degen_rate'])*100:.1f}%")
    if fl.get('top70_sniper_hold_rate') is not None:
        print(f"  top70狙击持仓: {float(fl['top70_sniper_hold_rate'])*100:.1f}%")
    if fl.get('vol24_liquidity_churn') is not None:
        print(f"  24h成交量/流动性: {fl['vol24_liquidity_churn']}x "
              f"({'洗盘嫌疑' if (fl['vol24_liquidity_churn'] or 0) > 5 else '正常'})")
    if fl.get('buys_sells_24h') and fl['buys_sells_24h'][0]:
        b, sel = fl['buys_sells_24h']
        print(f"  24h 买/卖笔数: {b}/{sel}")
    if fl.get('creator_created_count'):
        print(f"  创建者历史发币数: {fl['creator_created_count']} "
              f"({'批量发币工作室' if (fl['creator_created_count'] or 0) > 20 else ''})")
    if fl.get('image_dup_count'):
        print(f"  同图撞车币数量: {fl['image_dup_count']}")

    print(f"\n-- 真实用户明细 (top 10 by 持仓) --")
    for u in r['real_users_detail'][:10]:
        sig = ','.join(u['signals']) or '-'
        print(f"  {u['address'][:10]}... ${u['usd_value'] or 0:>8.0f}  "
              f"买{u['buy_tx']}笔  收益{u['profit'] or 0:>6.1%}  [{sig}]")


def main():
    ap = argparse.ArgumentParser(description='持币地址真实用户分析')
    ap.add_argument('--chain', default='bsc')
    ap.add_argument('--address')
    ap.add_argument('--info', help='已拉取的 token info raw JSON 文件')
    ap.add_argument('--holders', help='已拉取的 holders raw JSON 文件')
    ap.add_argument('--traders', help='已拉取的 traders raw JSON 文件')
    ap.add_argument('--dust', type=float, default=1.0, help='灰尘地址 USD 阈值 (默认 1)')
    args = ap.parse_args()

    if args.info or args.holders:
        info = load_json_arg(args.info) if args.info else {}
        holders = load_json_arg(args.holders) if args.holders else {'list': []}
    else:
        if not args.address:
            ap.error('需要 --address，或 --info/--holders 传本地 raw 数据')
        print(f"拉取 {args.chain}:{args.address} ...", file=sys.stderr)
        info = run_cli(['token', 'info', '--chain', args.chain,
                        '--address', args.address, '--raw'])
        holders = run_cli(['token', 'holders', '--chain', args.chain,
                           '--address', args.address, '--limit', '100', '--raw'])

    result = analyze(info, holders, None, args.dust)
    print_report(result)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    addr = (args.address or info.get('address') or 'unknown')[:10]
    ts = time.strftime('%Y%m%d_%H%M%S')
    out = OUT_DIR / f'holder_analysis_{args.chain}_{addr}_{ts}.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n详细结果: {out}")


if __name__ == '__main__':
    main()
