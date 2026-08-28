#!/usr/bin/env python3
"""
Solana 持币地址真实用户分析 - 从 GMGN 持仓数据里估算"真人"数量

理念：holder_count 不等于真实用户数。一个币显示 9 万个持有人，
其中可能包含：LP池、捆绑狙击机器人(bundler)、三明治机器人、
fresh wallet(女巫)、洗盘、纯转入的空投/内部分发地址、灰尘地址。
本脚本把这些人机信号逐层剥掉，估算"疑似真实用户"数量。

与 BSC 的关键差异（实测 pump.fun 代币得出）：
  1. maker_token_tags 里有 'bundler' 标签 -- SOL 最强的机器人信号，
     top100 里常见 60%+ 都是 bundler（买入笔数几十到几百笔、收益畸高）
  2. tags 里有 'sandwich_bot'（三明治机器人）
  3. pump.fun 代币 transfer_in 很普遍（bonding curve 机制），所以
     "纯转入"判定必须同时要求 buy_tx==0，不能只看有 transfer_in
  4. 'axiom'/'padre' 等 tags 是交易工具用户（真人用 App 交易的信号）
  5. 大盘子（holder>几千）时 top100 只覆盖鲸鱼筹码，不能按 top100
     比例外推全体 -- 改用全链统计率(bot/fresh rate)估算全体真实用户

数据源（gmgn-cli，脚本自动拉取，也可用 --info/--holders 传本地文件）：
  gmgn-cli token info    --chain sol --address <a> --raw
  gmgn-cli token holders --chain sol --address <a> --limit 100 --raw

剔除逻辑（按顺序判定，命中即归类，不再往下判）：
  1. pool/burn      addr_type==2 或有 exchange 字段（LP 池）
  2. suspicious     is_suspicious=true
  3. wash_trader    tags 含 wash_trader（洗盘）
  4. sandwich_bot   tags 含 sandwich_bot（三明治机器人，SOL 特有）
  5. sniper         tags/maker_token_tags 含 sniper
  6. bundler        maker_token_tags 含 bundler（捆绑狙击，SOL 特有）
  7. fresh_wallet   tags 含 fresh_wallet 或 is_new=true（女巫概率高）
  8. transfer_only  buy_tx_count_cur==0 且 transfer_in_count>0（内部分发/空投）
  9. dust           usd_value < 阈值（默认 $1，--dust 可调）
  其余 = 疑似真实用户

真实用户估算分两种模式（自动按筹码覆盖率切换）：
  - 覆盖率 >= 90%（小盘子）：按 top100 真实占比外推全体（同 BSC 逻辑）
  - 覆盖率 < 90%（大盘子/鲸鱼结构）：top100 只代表鲸鱼筹码结构，
    全体真实用户改用 holder_count x (1-bot_degen_rate) x (1-fresh_wallet_rate) 估算，
    两套数字并列展示，注明口径

用法：
  python3 analyze_sol_holders.py --address Ai66LHZG9MCzg1WKdawwqduVAXpNDUuV8M3uyq5ppump
  python3 analyze_sol_holders.py --address <ADDR> --dust 5
  python3 analyze_sol_holders.py --info info.json --holders holders.json
输出：
  终端打印中文报告；详细结果写 sol-holder-analysis/data/holder_analysis_<addr>_<ts>.json
"""

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

CHAIN = 'sol'
OUT_DIR = Path(__file__).resolve().parent / 'data'
# 小盘/大盘模式的筹码覆盖率分界
COVERAGE_THRESHOLD = 0.9


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

    if h.get('addr_type') == 2 or h.get('exchange'):
        return 'pool_burn', ['LP池地址']
    if h.get('is_suspicious'):
        return 'suspicious', ['GMGN标记可疑']
    if 'wash_trader' in tags:
        return 'wash_trader', ['洗盘交易者']
    if 'sandwich_bot' in tags:
        return 'sandwich_bot', ['三明治机器人']
    if 'sniper' in tags or 'sniper' in maker_tags:
        return 'sniper', ['狙击机器人']
    if 'bundler' in maker_tags:
        return 'bundler', ['捆绑狙击机器人']
    if 'fresh_wallet' in tags or h.get('is_new'):
        return 'fresh_wallet', ['新创建钱包(女巫概率高)']

    # 注意：pump.fun 代币 transfer_in 很普遍，必须 buy==0 才算纯转入
    buys = h.get('buy_tx_count_cur') or 0
    tin = h.get('transfer_in_count') or 0
    if buys == 0 and (tin > 0 or (h.get('current_transfer_in_amount') or 0) > 0):
        return 'transfer_only', ['零买入纯转入(内部分发/空投)']

    usd = float(h.get('usd_value') or 0)
    if usd < dust_usd:
        return 'dust', [f'持仓价值仅 ${usd:.2f}']

    return 'real_user', []


def quality_signals(h):
    """真实用户的质量信号（加分项）"""
    tags = set(h.get('tags') or [])
    sig = []
    tool_tags = {'gmgn', 'axiom', 'padre', 'photon', 'bullx'}
    tools = sorted(tags & tool_tags)
    if tools:
        sig.append('交易工具用户(' + ','.join(tools) + ')')
    if 'fomo' in tags:
        sig.append('散户fomo')
    if 'bluechip_owner' in tags:
        sig.append('蓝筹持有者')
    if h.get('twitter_username'):
        sig.append('twitter绑定')
    if (h.get('buy_tx_count_cur') or 0) >= 2:
        sig.append('有加仓行为')
    if float(h.get('native_balance') or 0) > 0:
        sig.append('有SOL余额')
    if 'kol' in tags:
        sig.append('KOL')
    return sig


def bundler_behavior(holders_list, liquidity):
    """bundler 行为分型 -- bundler 也有价值，但要看它在干什么而不是有多少个

    四种分型：
      exited_fast   卖出进度>=80%：快进快出的纯狙击者，利润已兑现、筹码已派发
      distributing  卖出进度20%-80%：正在缓慢派发，上涨会被持续卖给
      holding       卖出进度<20%且已实现收益>=0：拿了浮盈不卖，等更大行情
      re_entered    已实现收益<0：高位回补/加仓被套仍持有，最强的看多信号
    """
    bundlers = [h for h in holders_list if 'bundler' in (h.get('maker_token_tags') or [])]
    if not bundlers:
        return None

    types = {'exited_fast': [], 'distributing': [], 'holding': [], 're_entered': []}
    for h in bundlers:
        sell_pct = h.get('sell_amount_percentage') or 0
        realized = h.get('realized_profit') or 0
        if realized < 0:
            types['re_entered'].append(h)
        elif sell_pct >= 0.8:
            types['exited_fast'].append(h)
        elif sell_pct >= 0.2:
            types['distributing'].append(h)
        else:
            types['holding'].append(h)

    tot_buy = sum(h.get('buy_amount_cur') or 0 for h in bundlers)
    tot_sell = sum(h.get('sell_amount_cur') or 0 for h in bundlers)
    realized = sum(h.get('realized_profit') or 0 for h in bundlers)
    unrealized = sum(h.get('unrealized_profit') or 0 for h in bundlers)
    netflow = sum(h.get('netflow_usd') or 0 for h in bundlers)
    unreal_liq = (unrealized / liquidity) if liquidity else None

    if realized + unrealized != 0:
        realization_ratio = realized / (realized + unrealized)
    else:
        realization_ratio = 0.0

    return {
        'count': len(bundlers),
        'types': {k: len(v) for k, v in types.items()},
        'realized_profit_usd': round(realized),
        'unrealized_profit_usd': round(unrealized),
        'realization_ratio': round(realization_ratio, 4),
        'sell_progress': round(tot_sell / tot_buy, 4) if tot_buy else 0.0,
        'netflow_usd': round(netflow),
        'unrealized_over_liquidity': round(unreal_liq, 2) if unreal_liq is not None else None,
        'detail': {
            k: [{
                'address': h.get('address'),
                'usd_value': h.get('usd_value'),
                'sell_pct': h.get('sell_amount_percentage'),
                'realized': h.get('realized_profit'),
                'unrealized': h.get('unrealized_profit'),
                'netflow_usd': h.get('netflow_usd'),
            } for h in sorted(v, key=lambda x: -(x.get('realized_profit') or 0))]
            for k, v in types.items()
        },
    }


def analyze(info, holders, dust_usd):
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

    top_pct = sum(h.get('amount_percentage') or 0 for h in holders_list)
    top10_pct = sum(h.get('amount_percentage') or 0 for h in holders_list[:10])
    real_pct = sum(r['amount_percentage'] or 0 for r in real)
    coverage = top_pct

    bot_rate = float(stat.get('bot_degen_rate') or 0)
    fresh_rate = float(stat.get('fresh_wallet_rate') or 0)

    if coverage >= COVERAGE_THRESHOLD:
        # 小盘子：top100 基本代表全体，按真实占比外推
        mode = 'top_ratio'
        if holder_count > n:
            est_total = cats['real_user'] + round((holder_count - n) * real_ratio)
        else:
            est_total = cats['real_user']
        est_note = 'top持仓覆盖率>=90%，按真实占比外推'
    else:
        # 大盘子：top100 只是鲸鱼结构，全体用全链统计率估算
        mode = 'stat_rates'
        est_total = round(holder_count * (1 - bot_rate) * (1 - fresh_rate))
        est_note = (f'top持仓仅覆盖{coverage*100:.0f}%筹码(鲸鱼结构)，'
                    f'全体按 holder_count x (1-机器人率{bot_rate:.2f}) x (1-新钱包率{fresh_rate:.2f}) 估算')

    vol24 = float(price_info.get('volume_24h') or 0)
    liq = float(info.get('liquidity') or 0)
    churn = round(vol24 / liq, 1) if liq else None

    buys24 = price_info.get('buys_24h')
    sells24 = price_info.get('sells_24h')
    avg_tx = None
    if holder_count and buys24 is not None and sells24 is not None:
        avg_tx = round((int(buys24) + int(sells24)) / holder_count, 2)
    buys1h = price_info.get('buys_1h')
    sells1h = price_info.get('sells_1h')
    swaps_per_min_1h = None
    if buys1h is not None or sells1h is not None:
        swaps_per_min_1h = round(((int(buys1h or 0) + int(sells1h or 0)) / 60.0), 1)
    real_buys = [int(r.get('buy_tx') or 0) for r in real]
    real_buy_med = None
    if real_buys:
        real_buys_sorted = sorted(real_buys)
        mid = len(real_buys_sorted) // 2
        real_buy_med = (real_buys_sorted[mid] if len(real_buys_sorted) % 2
                        else (real_buys_sorted[mid - 1] + real_buys_sorted[mid]) / 2)

    result = {
        'token': {
            'symbol': info.get('symbol'), 'name': info.get('name'),
            'chain': CHAIN, 'address': info.get('address'),
            'holder_count': holder_count, 'liquidity_usd': liq,
            'launchpad': info.get('launchpad'),
        },
        'sample': {'holders_fetched': n, 'supply_coverage': round(coverage, 4)},
        'classification': dict(cats),
        'exclude_reasons': dict(reasons_all),
        'bundler_behavior': bundler_behavior(holders_list, liq),
        'real_user_estimate': {
            'mode': mode,
            'note': est_note,
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
            'bundler_trader_rate': stat.get('top_bundler_trader_percentage'),
            'entrapment_trader_rate': stat.get('top_entrapment_trader_percentage'),
            'top70_sniper_hold_rate': stat.get('top70_sniper_hold_rate'),
            'wallet_tags_stat': wts,
            'vol24_liquidity_churn': churn,
            'buys_sells_24h': [buys24, sells24],
            'avg_tx_per_holder': avg_tx,
            'swaps_per_min_1h': swaps_per_min_1h,
            'real_holder_buy_tx_median': real_buy_med,
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

    print(f"\n===== {t['name']} ({t['symbol']}) SOL 持币真实用户分析 =====")
    print(f"官方 holder_count: {t['holder_count']:,}   流动性: ${t['liquidity_usd']:,.0f}   launchpad: {t['launchpad']}")
    print(f"样本: top {s['holders_fetched']} 持仓, 覆盖筹码 {s['supply_coverage']*100:.1f}%")

    print(f"\n-- 持仓分类 (top {s['holders_fetched']}, 鲸鱼筹码结构) --")
    label = {
        'pool_burn': 'LP池', 'suspicious': '可疑地址', 'wash_trader': '洗盘',
        'sandwich_bot': '三明治机器人', 'sniper': '狙击机器人', 'bundler': '捆绑机器人',
        'fresh_wallet': '新钱包(女巫)', 'transfer_only': '纯转入(分发/空投)',
        'dust': '灰尘地址', 'real_user': '疑似真实用户',
    }
    for k in ('pool_burn', 'suspicious', 'wash_trader', 'sandwich_bot', 'sniper',
              'bundler', 'fresh_wallet', 'transfer_only', 'dust', 'real_user'):
        if c.get(k):
            print(f"  {label[k]:<14} {c[k]:>4}  ({c[k]/s['holders_fetched']*100:.0f}%)")

    print(f"\n-- 真实用户估算 ({est['mode']}) --")
    print(f"  [{est['note']}]")
    print(f"  top持仓中真实用户: {est['in_top_holders']} 个 (占非池地址 {est['real_ratio_of_non_pool']*100:.1f}%)")
    print(f"  全体估算: ~{est['extrapolated_total']:,} 个真实用户 (官方 holder_count={t['holder_count']:,})")
    print(f"  真实用户持有筹码: {est['real_supply_pct']*100:.1f}%")

    print(f"\n-- 全链警示信号 --")
    if fl.get('fresh_wallet_rate') is not None:
        print(f"  新钱包比例: {float(fl['fresh_wallet_rate'])*100:.1f}%")
    if fl.get('bot_degen_rate') is not None:
        print(f"  机器人交易比例: {float(fl['bot_degen_rate'])*100:.1f}%")
    if fl.get('bundler_trader_rate'):
        print(f"  捆绑交易者比例: {float(fl['bundler_trader_rate'])*100:.1f}%")
    if fl.get('entrapment_trader_rate'):
        print(f"  套牢盘交易者比例: {float(fl['entrapment_trader_rate'])*100:.1f}%")
    if fl.get('top70_sniper_hold_rate') is not None:
        print(f"  top70狙击持仓: {float(fl['top70_sniper_hold_rate'])*100:.1f}%")
    if fl.get('vol24_liquidity_churn') is not None:
        print(f"  24h成交量/流动性: {fl['vol24_liquidity_churn']}x "
              f"({'洗盘嫌疑' if (fl['vol24_liquidity_churn'] or 0) > 5 else '正常'})")
    if fl.get('buys_sells_24h') and fl['buys_sells_24h'][0]:
        b, sel = fl['buys_sells_24h']
        print(f"  24h 买/卖笔数: {b:,}/{sel:,}")
    if fl.get('avg_tx_per_holder') is not None:
        a = fl['avg_tx_per_holder']
        note = '小单刷屏嫌疑' if a > 8 else '正常'
        if a > 12:
            note = '过热/对倒嫌疑'
        print(f"  人均成交(24h笔数/holder): {a}  ({note}；>8 警示，>12 偏对倒)")
    if fl.get('swaps_per_min_1h') is not None:
        spm = fl['swaps_per_min_1h']
        note = '过热' if spm > 80 else ('热盘' if spm > 30 else '正常')
        print(f"  近1h 笔数/分钟: {spm}  ({note}；当下密不密，24h 人均看不出这一小时)")
    if fl.get('real_holder_buy_tx_median') is not None:
        print(f"  样本疑似真人买入笔数中位数: {fl['real_holder_buy_tx_median']}")
    if fl.get('creator_created_count'):
        print(f"  创建者历史发币数: {fl['creator_created_count']:,} "
              f"({'批量发币工作室' if (fl['creator_created_count'] or 0) > 20 else ''})")
    if fl.get('image_dup_count'):
        print(f"  同图撞车币数量: {fl['image_dup_count']}")

    bb = r.get('bundler_behavior')
    if bb:
        print(f"\n-- bundler 行为分型 ({bb['count']} 个) --")
        tlabel = {
            'exited_fast': '快进快出(卖>=80%)',
            'distributing': '缓慢派发(卖20-80%)',
            'holding': '持仓待发(卖<20%)',
            're_entered': '高位回补被套仍持有',
        }
        for k in ('exited_fast', 'distributing', 'holding', 're_entered'):
            if bb['types'].get(k):
                print(f"  {tlabel[k]:<20} {bb['types'][k]:>3}")
        print(f"  已实现收益: ${bb['realized_profit_usd']:,.0f} vs "
              f"未实现: ${bb['unrealized_profit_usd']:,.0f} "
              f"(仅兑现 {bb['realization_ratio']*100:.0f}%)")
        print(f"  整体卖出进度: {bb['sell_progress']*100:.0f}%   净流入: ${bb['netflow_usd']:,.0f}")
        if bb.get('unrealized_over_liquidity') is not None:
            ratio = bb['unrealized_over_liquidity']
            print(f"  未实现利润/流动性: {ratio}x "
                  f"({'远超流动性承载力，无法一次性退出' if ratio > 1 else '流动性可承接'})")
        # 读法
        types = bb['types']
        if types.get('re_entered', 0) >= 5 or bb['sell_progress'] < 0.5:
            verdict = '偏看多：bundler 未急于兑现，有回补/净加仓迹象'
        elif types.get('exited_fast', 0) >= bb['count'] * 0.5:
            verdict = '偏看空：多数 bundler 已完成派发离场'
        else:
            verdict = '中性：bundler 仍在缓慢派发，上涨面临持续抛压'
        print(f"  -> {verdict}")


    print(f"\n-- 真实用户明细 (top 10 by 持仓) --")
    for u in r['real_users_detail'][:10]:
        sig = ','.join(u['signals']) or '-'
        print(f"  {u['address'][:8]}... ${u['usd_value'] or 0:>10,.0f}  "
              f"买{u['buy_tx']}笔  收益{u['profit'] or 0:>8.1%}  [{sig}]")


def main():
    ap = argparse.ArgumentParser(description='SOL 持币地址真实用户分析')
    ap.add_argument('--address', help='SOL 代币合约地址')
    ap.add_argument('--info', help='已拉取的 token info raw JSON 文件')
    ap.add_argument('--holders', help='已拉取的 holders raw JSON 文件')
    ap.add_argument('--dust', type=float, default=1.0, help='灰尘地址 USD 阈值 (默认 1)')
    args = ap.parse_args()

    if args.info or args.holders:
        info = load_json_arg(args.info) if args.info else {}
        holders = load_json_arg(args.holders) if args.holders else {'list': []}
    else:
        if not args.address:
            ap.error('需要 --address，或 --info/--holders 传本地 raw 数据')
        print(f"拉取 sol:{args.address} ...", file=sys.stderr)
        info = run_cli(['token', 'info', '--chain', CHAIN,
                        '--address', args.address, '--raw'])
        holders = run_cli(['token', 'holders', '--chain', CHAIN,
                           '--address', args.address, '--limit', '100', '--raw'])

    result = analyze(info, holders, args.dust)
    print_report(result)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    addr = (args.address or info.get('address') or 'unknown')[:10]
    ts = time.strftime('%Y%m%d_%H%M%S')
    out = OUT_DIR / f'holder_analysis_{addr}_{ts}.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n详细结果: {out}")


if __name__ == '__main__':
    main()
