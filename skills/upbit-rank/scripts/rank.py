#!/usr/bin/env python3
"""拉取 Upbit 公开行情，输出 24h 成交额榜和涨幅榜。"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any

API_BASE = "https://api.upbit.com"
FALLBACK_HTTP_PROXY = "http://127.0.0.1:7897"


def _proxy_candidates(explicit: str | None) -> list[str | None]:
    seen: list[str | None] = []
    for item in (
        explicit,
        os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"),
        os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"),
        FALLBACK_HTTP_PROXY,
        None,
    ):
        if item not in seen:
            seen.append(item)
    return seen


def fetch_json_urllib(
    url: str, proxy: str | None, timeout: float, insecure: bool
) -> Any:
    handlers = []
    if proxy:
        handlers.append(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    if insecure:
        handlers.append(
            urllib.request.HTTPSHandler(context=ssl._create_unverified_context())
        )
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "upbit-rank/1.0"},
    )
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_json_curl(url: str, proxy: str | None, timeout: float) -> Any:
    cmd = [
        "curl",
        "-sS",
        "--fail",
        "--connect-timeout",
        str(max(1, int(timeout))),
        "--max-time",
        str(max(2, int(timeout) + 5)),
        "-H",
        "Accept: application/json",
        "-H",
        "User-Agent: upbit-rank/1.0",
        url,
    ]
    env = os.environ.copy()
    if proxy:
        cmd[1:1] = ["-x", proxy]
        env["https_proxy"] = proxy
        env["http_proxy"] = proxy
        env["HTTPS_PROXY"] = proxy
        env["HTTP_PROXY"] = proxy
    result = subprocess.run(
        cmd, capture_output=True, text=True, env=env, check=False
    )
    if result.returncode != 0:
        raise OSError(result.stderr.strip() or f"curl exit {result.returncode}")
    return json.loads(result.stdout)


def fetch_with_fallback(url: str, explicit_proxy: str | None, timeout: float) -> Any:
    errors: list[str] = []
    for proxy in _proxy_candidates(explicit_proxy):
        label = proxy or "直连"
        try:
            return fetch_json_curl(url, proxy, timeout)
        except (OSError, json.JSONDecodeError, FileNotFoundError) as exc:
            errors.append(f"curl/{label}: {exc}")
        for insecure in (False, True):
            try:
                return fetch_json_urllib(url, proxy, timeout, insecure)
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                mode = "insecure" if insecure else "tls"
                errors.append(f"urllib/{mode}/{label}: {exc}")
    raise RuntimeError("无法连接 Upbit API。已尝试：\n- " + "\n- ".join(errors))


def fmt_krw(value: float) -> str:
    abs_v = abs(value)
    if abs_v >= 1e12:
        return f"{value / 1e12:.2f} 万亿 KRW"
    if abs_v >= 1e8:
        return f"{value / 1e8:.2f} 亿 KRW"
    if abs_v >= 1e4:
        return f"{value / 1e4:.2f} 万 KRW"
    return f"{value:,.0f} KRW"


def fmt_pct(rate: float) -> str:
    return f"{rate * 100:+.2f}%"


def fmt_num(value: float) -> str:
    if abs(value) >= 1:
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    return f"{value:.8f}".rstrip("0").rstrip(".")


def pick_symbol(market: str) -> str:
    _, _, rest = market.partition("-")
    return rest or market


def build_rows(
    tickers: list[dict[str, Any]],
    names: dict[str, dict[str, str]],
    quote: str,
) -> list[dict[str, Any]]:
    prefix = f"{quote}-"
    rows = []
    for t in tickers:
        market = t.get("market") or ""
        if not market.startswith(prefix):
            continue
        change_rate = float(t.get("signed_change_rate") or 0)
        vol_quote = float(t.get("acc_trade_price_24h") or 0)
        vol_base = float(t.get("acc_trade_volume_24h") or 0)
        price = float(t.get("trade_price") or 0)
        meta = names.get(market, {})
        rows.append(
            {
                "market": market,
                "symbol": pick_symbol(market),
                "korean_name": meta.get("korean_name", ""),
                "english_name": meta.get("english_name", ""),
                "market_warning": meta.get("market_warning", "NONE"),
                "trade_price": price,
                "signed_change_rate": change_rate,
                "change_pct": round(change_rate * 100, 4),
                "acc_trade_price_24h": vol_quote,
                "acc_trade_volume_24h": vol_base,
            }
        )
    return rows


def to_view(row: dict[str, Any], rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "market": row["market"],
        "symbol": row["symbol"],
        "name": row["english_name"] or row["korean_name"] or row["symbol"],
        "korean_name": row["korean_name"],
        "price": row["trade_price"],
        "price_text": fmt_num(row["trade_price"]),
        "change_pct": row["change_pct"],
        "change_text": fmt_pct(row["signed_change_rate"]),
        "volume_quote_24h": row["acc_trade_price_24h"],
        "volume_quote_text": fmt_krw(row["acc_trade_price_24h"]),
        "volume_base_24h": row["acc_trade_volume_24h"],
        "volume_base_text": fmt_num(row["acc_trade_volume_24h"]),
        "warning": row["market_warning"] != "NONE",
        "market_warning": row["market_warning"],
    }


def markdown_table(title: str, rows: list[dict[str, Any]], quote: str) -> str:
    lines = [
        f"### {title}",
        "",
        f"| 排名 | 交易对 | 名称 | 现价 ({quote}) | 涨跌 | 24h 成交额 | 24h 成交量 |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for r in rows:
        warn = " ⚠" if r["warning"] else ""
        lines.append(
            f"| {r['rank']} | `{r['market']}`{warn} | {r['name']} | {r['price_text']} | {r['change_text']} | {r['volume_quote_text']} | {r['volume_base_text']} |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Upbit 24h 成交额榜 / 涨幅榜")
    parser.add_argument("--quote", default="KRW", help="报价货币，默认 KRW")
    parser.add_argument("--top", type=int, default=10, help="每榜条数，默认 10")
    parser.add_argument("--proxy", default=None, help="HTTP 代理，如 http://127.0.0.1:7897")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="输出格式",
    )
    args = parser.parse_args()
    quote = args.quote.upper()
    top_n = max(1, args.top)

    markets = fetch_with_fallback(
        f"{API_BASE}/v1/market/all?isDetails=true", args.proxy, args.timeout
    )
    tickers = fetch_with_fallback(
        f"{API_BASE}/v1/ticker/all?quote_currencies={quote}",
        args.proxy,
        args.timeout,
    )
    names = {
        m["market"]: {
            "korean_name": m.get("korean_name") or "",
            "english_name": m.get("english_name") or "",
            "market_warning": m.get("market_warning") or "NONE",
        }
        for m in markets
        if isinstance(m, dict) and m.get("market")
    }
    rows = build_rows(tickers, names, quote)
    if not rows:
        print(f"未找到 {quote} 市场数据", file=sys.stderr)
        return 1

    volume_sorted = sorted(rows, key=lambda r: r["acc_trade_price_24h"], reverse=True)
    gainer_sorted = sorted(rows, key=lambda r: r["signed_change_rate"], reverse=True)
    volume_top = [to_view(r, i) for i, r in enumerate(volume_sorted[:top_n], 1)]
    gainers_top = [to_view(r, i) for i, r in enumerate(gainer_sorted[:top_n], 1)]

    payload = {
        "exchange": "Upbit",
        "quote": quote,
        "market_count": len(rows),
        "note": "成交额/成交量为滚动 24 小时；涨跌幅相对前一日 UTC 收盘价（与 Upbit 行情页一致）。",
        "volume_top": volume_top,
        "gainers_top": gainers_top,
    }

    if args.format == "json":
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0

    print(f"# Upbit {quote} 行情榜")
    print()
    print(payload["note"])
    print(f"覆盖交易对：{len(rows)} 个")
    print()
    print(markdown_table(f"24h 成交额 Top {top_n}", volume_top, quote))
    print()
    print(markdown_table(f"涨幅榜 Top {top_n}", gainers_top, quote))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
