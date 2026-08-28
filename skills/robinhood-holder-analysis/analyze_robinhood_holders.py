#!/usr/bin/env python3
"""
Robinhood Chain 持币真实用户分析 - 从 GMGN 持仓数据里估算"真人"数量

理念：holder_count 不等于真实用户数。一个显示 200 持有人的币，
里面可能有 LP 池、捆绑钱包、fresh wallet、洗盘/狙击机器人、灰尘地址。
本脚本把这些人机信号逐层剥掉，估算"疑似真实用户"数量。

数据源（gmgn-cli，脚本自动拉取，也可用 --info/--holders 传本地文件）：
  gmgn-cli token info    --chain robinhood --address <a> --raw
  gmgn-cli token holders --chain robinhood --address <a> --limit 100 --raw

用法：
  python3 analyze_robinhood_holders.py --address 0xfe242d1da8fd04f6a1f80b6d3d807b02e062ad4e
  python3 analyze_robinhood_holders.py --address 0x... --dust 5
  python3 analyze_robinhood_holders.py --info info.json --holders holders.json
输出：
  终端打印中文报告；详细结果写 robinhood-holder-analysis/data/holder_analysis_<addr>_<ts>.json
"""

import argparse
import json
import ssl
import subprocess
import sys
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

CHAIN = 'robinhood'
OUT_DIR = Path(__file__).resolve().parent / 'data'

BURN_ADDRESSES = {
    '0x0000000000000000000000000000000000000000',
    '0x000000000000000000000000000000000000dead',
    '0x0000000000000000000000000000000000000001',
}


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / '_shared'))
from env import cli_env  # 读本项目 .env，不再用仓库外路径


def _cli_rejected_chain(stderr: str) -> bool:
    s = (stderr or '').lower()
    return 'invalid chain' in s and 'robinhood' in s


def gmgn_http(path: str, query: dict) -> dict:
    """本机 gmgn-cli 1.1.x 还不认 robinhood，直接打 OpenAPI。"""
    env = cli_env()
    api_key = (env.get('GMGN_API_KEY') or '').strip()
    if not api_key:
        sys.exit('缺少 GMGN_API_KEY')
    host = (env.get('GMGN_HOST') or 'https://openapi.gmgn.ai').rstrip('/')
    q = {k: v for k, v in query.items() if v is not None}
    q['timestamp'] = str(int(time.time()))
    q['client_id'] = str(uuid.uuid4())
    url = f'{host}{path}?{urllib.parse.urlencode(q)}'
    headers = {'X-APIKEY': api_key, 'Content-Type': 'application/json'}
    req = urllib.request.Request(url, headers=headers, method='GET')
    handlers = []
    proxy = (env.get('HTTPS_PROXY') or env.get('HTTP_PROXY') or '').strip()
    if proxy:
        handlers.append(urllib.request.ProxyHandler({'http': proxy, 'https': proxy}))
    # 本地代理常做 TLS 中间人，系统 CA 验不过
    ctx = ssl._create_unverified_context()
    handlers.append(urllib.request.HTTPSHandler(context=ctx))
    opener = urllib.request.build_opener(*handlers)
    try:
        with opener.open(req, timeout=45) as resp:
            payload = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')[:500]
        sys.exit(f'GMGN HTTP {e.code} {path}: {body}')
    except urllib.error.URLError as e:
        sys.exit(f'GMGN 网络失败 {path}: {e.reason}')
    if payload.get('code') not in (0, None):
        sys.exit(f"GMGN {path} code={payload.get('code')} {payload.get('message') or payload.get('error') or ''}")
    return payload.get('data', payload)


def run_cli(args):
    """优先 gmgn-cli；若本机版本拒认 robinhood，回退 OpenAPI。"""
    env = cli_env()
    p = subprocess.run(['gmgn-cli'] + args, capture_output=True, text=True, env=env)
    out = p.stdout.strip()
    i = out.find('{')
    if i >= 0:
        return json.loads(out[i:])
    err = (p.stderr or '').strip()
    if _cli_rejected_chain(err):
        print('本机 gmgn-cli 不支持 robinhood，改用其 OpenAPI 客户端 ...', file=sys.stderr)
        cmd = None
        address = None
        limit = '100'
        it = iter(args)
        for a in it:
            if a == 'token':
                cmd = next(it, None)
            elif a == '--address':
                address = next(it, None)
            elif a == '--limit':
                limit = next(it, None)
        if cmd not in ('info', 'holders') or not address:
            sys.exit(f'无法映射 gmgn-cli 参数: {args}')
        helper = Path(__file__).resolve().parent / 'fetch_via_installed_cli.mjs'
        p2 = subprocess.run(
            ['node', str(helper), cmd, address, str(limit)],
            capture_output=True, text=True, env=env,
            cwd=str(Path(__file__).resolve().parents[2]),
        )
        out2 = (p2.stdout or '').strip()
        j = out2.find('{')
        if j >= 0:
            return json.loads(out2[j:])
        err2 = (p2.stderr or out2 or '').strip()
        print(f'OpenAPI 客户端失败，再试 HTTP: {err2[:400]}', file=sys.stderr)
        return gmgn_http(
            '/v1/token/info' if cmd == 'info' else '/v1/market/token_top_holders',
            {'chain': 'robinhood', 'address': address, 'limit': limit},
        )
    print(f"gmgn-cli {' '.join(args)} 未返回 JSON", file=sys.stderr)
    if err:
        print(err[:500], file=sys.stderr)
    sys.exit(1)


def load_json_arg(path):
    raw = Path(path).read_text()
    i = raw.find('{')
    return json.loads(raw[i:])


def classify_holder(h, dust_usd):
    """返回 (类别, 原因列表)。命中剔除规则即返回，不再继续判。"""
    tags = set(h.get('tags') or [])
    maker_tags = set(h.get('maker_token_tags') or [])
    addr = (h.get('address') or '').lower()

    if h.get('addr_type') == 2 or h.get('exchange') or addr in BURN_ADDRESSES:
        return 'pool_burn', ['LP池/销毁地址']
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
        sig.append('有ETH余额')
    if 'kol' in tags:
        sig.append('KOL')
    return sig


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
    classified = []
    for h in holders_list:
        cat, reasons = classify_holder(h, dust_usd)
        cats[cat] += 1
        for r in reasons:
            reasons_all[r] += 1
        classified.append({
            'address': h.get('address'),
            'cat': cat,
            'usd_value': h.get('usd_value'),
            'amount_percentage': h.get('amount_percentage'),
            'buy_tx': h.get('buy_tx_count_cur'),
            'tags': h.get('tags') or [],
        })
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
            'buys_sells_24h': [buys24, sells24],
            'avg_tx_per_holder': avg_tx,
            'swaps_per_min_1h': swaps_per_min_1h,
            'real_holder_buy_tx_median': real_buy_med,
            'creator_created_count': dev.get('creator_created_count'),
            'image_dup_count': info.get('image_dup_count'),
        },
        'real_users_detail': sorted(real, key=lambda r: -(r['usd_value'] or 0)),
        'top_holders': classified,
    }
    return result


def print_report(r):
    t = r['token']
    s = r['sample']
    est = r['real_user_estimate']
    c = r['classification']
    fl = r['chain_flags']
    n = s['holders_fetched'] or 1

    print(f"\n===== {t['name']} ({t['symbol']}) Robinhood 持币真实用户分析 =====")
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
            print(f"  {label[k]:<14} {c[k]:>4}  ({c[k]/n*100:.0f}%)")

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
        print(f"  创建者历史发币数: {fl['creator_created_count']} "
              f"({'批量发币工作室' if (fl['creator_created_count'] or 0) > 20 else ''})")
    if fl.get('image_dup_count'):
        print(f"  同图撞车币数量: {fl['image_dup_count']}")

    print(f"\n-- 真实用户明细 (top 10 by 持仓) --")
    for u in r['real_users_detail'][:10]:
        sig = ','.join(u['signals']) or '-'
        pct = (u.get('amount_percentage') or 0) * 100
        print(f"  {u['address'][:10]}... ${u['usd_value'] or 0:>8.0f}  "
              f"{pct:>5.2f}%  买{u['buy_tx']}笔  利润${u['profit'] or 0:,.0f}  [{sig}]")


def main():
    ap = argparse.ArgumentParser(description='Robinhood Chain 持币地址真实用户分析')
    ap.add_argument('--address', help='Robinhood 代币合约地址（0x）')
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
        print(f"拉取 robinhood:{args.address} ...", file=sys.stderr)
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
