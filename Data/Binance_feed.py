import requests
from datetime import datetime

def compute_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas[-period:]]
    losses = [-d if d < 0 else 0 for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_gain/avg_loss)), 2)

def compute_ema(closes, period):
    if len(closes) < period:
        return closes[-1]
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = price * k + ema * (1 - k)
    return round(ema, 4)

def compute_macd(closes):
    if len(closes) < 26:
        return 0, 0, 0
    ema12 = compute_ema(closes, 12)
    ema26 = compute_ema(closes, 26)
    macd = round(ema12 - ema26, 4)
    vals = []
    for i in range(26, len(closes)):
        vals.append(compute_ema(closes[:i+1], 12) - compute_ema(closes[:i+1], 26))
    signal = compute_ema(vals, 9) if len(vals) >= 9 else macd
    return macd, round(signal, 4), round(macd - signal, 4)

def compute_bollinger(closes, period=20):
    if len(closes) < period:
        p = closes[-1]
        return p, p, p
    w = closes[-period:]
    mid = sum(w) / period
    std = (sum((x-mid)**2 for x in w) / period) ** 0.5
    return round(mid+2*std, 4), round(mid, 4), round(mid-2*std, 4)

def compute_atr(highs, lows, closes, period=14):
    if len(closes) < 2:
        return 0
    trs = []
    for i in range(1, min(len(closes), period+1)):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        trs.append(tr)
    return round(sum(trs)/len(trs), 4) if trs else 0

def get_fear_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=8)
        d = r.json()["data"][0]
        return {"value": int(d["value"]), "label": d["value_classification"]}
    except:
        return {"value": 50, "label": "Neutral"}

def fetch_market_data(symbol="BTCUSDT", interval="1h"):
    print(f"Fetching {symbol}...")
    base = "https://api.binance.com"
    raw = requests.get(f"{base}/api/v3/klines", params={"symbol": symbol, "interval": interval, "limit": 100}, timeout=10).json()
    highs = [float(k[2]) for k in raw]
    lows = [float(k[3]) for k in raw]
    closes = [float(k[4]) for k in raw]
    ticker = requests.get(f"{base}/api/v3/ticker/24hr", params={"symbol": symbol}, timeout=10).json()
    price = float(ticker["lastPrice"])
    ob = requests.get(f"{base}/api/v3/depth", params={"symbol": symbol, "limit": 50}, timeout=10).json()
    bids = [[float(p), float(q)] for p, q in ob.get("bids", [])]
    asks = [[float(p), float(q)] for p, q in ob.get("asks", [])]
    best_bid = bids[0][0] if bids else 0
    best_ask = asks[0][0] if asks else 0
    spread = round((best_ask-best_bid)/best_bid*100, 4) if best_bid else 0
    mid = (best_bid+best_ask)/2
    t = mid*0.01
    bid_d = sum(p*q for p,q in bids if abs(p-mid)<=t)
    ask_d = sum(p*q for p,q in asks if abs(p-mid)<=t)
    ratio = round(bid_d/ask_d, 3) if ask_d > 0 else 1.0
    fg = get_fear_greed()
    fgv = fg["value"]
    if fgv >= 75: lbl, sc = "Extreme Greed", 8
    elif fgv >= 55: lbl, sc = "Greed", 7
    elif fgv >= 45: lbl, sc = "Neutral", 5
    elif fgv >= 25: lbl, sc = "Fear", 3
    else: lbl, sc = "Extreme Fear", 2
    coin = symbol.replace("USDT","")
    cmc = {}
    whales = {}
    try:
        from data.cmc_feed import fetch_cmc_data
        cmc = fetch_cmc_data(coin)
    except Exception as e:
        print(f"CMC error: {e}")
    try:
        from data.whale_feed import fetch_whale_data
        whales = fetch_whale_data(coin)
    except Exception as e:
        print(f"Whale error: {e}")
    return {
        "symbol": f"{coin}/USDT",
        "price": price,
        "indicators": {
            "rsi": compute_rsi(closes),
            "macd": compute_macd(closes)[0],
            "macd_signal": compute_macd(closes)[1],
            "macd_hist": compute_macd(closes)[2],
            "ema_20": compute_ema(closes, 20),
            "ema_50": compute_ema(closes, 50),
            "bb_upper": compute_bollinger(closes)[0],
            "bb_mid": compute_bollinger(closes)[1],
            "bb_lower": compute_bollinger(closes)[2],
            "atr": compute_atr(highs, lows, closes),
            "volume_24h": f"${float(ticker['volume'])*price:,.0f}",
            "volume_change_pct": round(float(ticker.get("priceChangePercent",0)),2)
        },
        "orderbook": {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread_pct": spread,
            "bid_depth_1pct": round(bid_d),
            "ask_depth_1pct": round(ask_d),
            "buy_sell_ratio": ratio
        },
        "sentiment": {
            "overall": lbl,
            "score": sc,
            "fear_greed": f"{fgv} - {fg['label']}",
            "headlines": cmc.get("news", [])[:6]
        },
        "cmc": cmc,
        "whales": whales,
        "raw": {"closes": closes[-20:]}
    }
