import os
import time
import requests

EXCHANGES = {"binance","coinbase","kraken","bitfinex","huobi","okx","kucoin","bybit","gemini","bitstamp"}

def _key():
    return os.environ.get("WHALE_ALERT_API_KEY","").strip()

def _has_key():
    return bool(_key())

def _fmt(val):
    if not val: return "$0"
    if val >= 1e9: return f"${val/1e9:.2f}B"
    elif val >= 1e6: return f"${val/1e6:.1f}M"
    elif val >= 1e3: return f"${val/1e3:.0f}K"
    return f"${val:,.0f}"

def _signal(fl, tl):
    fe = any(ex in fl for ex in EXCHANGES)
    te = any(ex in tl for ex in EXCHANGES)
    if not fe and te: return "BEARISH"
    elif fe and not te: return "BULLISH"
    return "NEUTRAL"

def _describe(sym, amt, usd, fl, tl):
    sig = _signal(fl, tl)
    icon = "🔴" if sig=="BEARISH" else "🟢" if sig=="BULLISH" else "⚪"
    return f"{icon} {amt:,.0f} {sym} ({_fmt(usd)}): {fl} to {tl}"

def _ago(ts):
    try:
        diff = int(time.time()) - int(ts)
        mins = diff // 60
        return f"{mins}m ago" if mins < 60 else f"{mins//60}h ago"
    except:
        return "recently"

def get_transactions(symbol="BTC", min_usd=500000):
    if not _has_key():
        return []
    try:
        r = requests.get(
            "https://api.whale-alert.io/v1/transactions",
            params={
                "api_key": _key(),
                "min_value": min_usd,
                "limit": 20,
                "start": int(time.time()) - 3600,
                "currency": symbol.lower()
            },
            timeout=10
        )
        r.raise_for_status()
        result = []
        for tx in r.json().get("transactions",[]):
            fi = tx.get("from",{})
            ti = tx.get("to",{})
            fl = (fi.get("owner_type") or fi.get("owner") or "unknown").lower()
            tl = (ti.get("owner_type") or ti.get("owner") or "unknown").lower()
            sym = tx.get("symbol","").upper()
            amt = tx.get("amount",0)
            usd = tx.get("amount_usd",0)
            result.append({
                "symbol": sym,
                "amount": amt,
                "usd_value": usd,
                "from": fl,
                "to": tl,
                "signal": _signal(fl,tl),
                "description": _describe(sym,amt,usd,fl,tl),
                "age": _ago(tx.get("timestamp",0))
            })
        return result
    except Exception as e:
        print(f"  Whale error: {e}")
        return []

def fetch_whale_data(symbol="BTC", min_usd=500000):
    print(f"  Fetching whale data for {symbol}...")
    all_txs = []
    for coin in list({symbol,"BTC","ETH","USDT"}):
        all_txs.extend(get_transactions(coin, min_usd))
    coin_txs = [t for t in all_txs if t["symbol"]==symbol.upper()]
    bullish = [t for t in coin_txs if t["signal"]=="BULLISH"]
    bearish = [t for t in coin_txs if t["signal"]=="BEARISH"]
    total_usd = sum(t["usd_value"] for t in coin_txs)
    bull_usd = sum(t["usd_value"] for t in bullish)
    bear_usd = sum(t["usd_value"] for t in bearish)
    if bear_usd > bull_usd * 1.5:
        net = "BEARISH"
        detail = f"Heavy exchange inflows: {_fmt(bear_usd)}"
    elif bull_usd > bear_usd * 1.5:
        net = "BULLISH"
        detail = f"Strong accumulation: {_fmt(bull_usd)}"
    else:
        net = "NEUTRAL"
        detail = f"Mixed: {_fmt(bull_usd)} withdrawn, {_fmt(bear_usd)} deposited"
    stables = [t for t in all_txs if t["symbol"] in ("USDT","USDC","BUSD")]
    stable_usd = sum(t["usd_value"] for t in stables)
    all_bear = sum(t["usd_value"] for t in all_txs if t["signal"]=="BEARISH")
    all_bull = sum(t["usd_value"] for t in all_txs if t["signal"]=="BULLISH")
    return {
        "transaction_count": len(coin_txs),
        "total_usd_moved": _fmt(total_usd),
        "bullish_count": len(bullish),
        "bearish_count": len(bearish),
        "net_signal": net,
        "net_signal_detail": detail,
        "exchange_inflows": _fmt(bear_usd),
        "exchange_outflows": _fmt(bull_usd),
        "transactions": [t["description"] for t in coin_txs[:8]],
        "largest_tx": max(coin_txs, key=lambda t: t["usd_value"])["description"] if coin_txs else "N/A",
        "market_wide": {
            "all_exchange_inflows": _fmt(all_bear),
            "all_exchange_outflows": _fmt(all_bull),
            "stablecoin_moves": _fmt(stable_usd),
            "stablecoin_note": "Large stablecoin inflows = buying pressure" if stable_usd > 50000000 else "",
            "total_txs_tracked": len(all_txs)
        },
        "has_api_key": _has_key()
    }
