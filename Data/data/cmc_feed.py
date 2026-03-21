import os
import requests
from datetime import datetime, timezone

def _has_key():
    return bool(os.environ.get("CMC_API_KEY","").strip())

def _headers():
    return {"X-CMC_PRO_API_KEY": os.environ.get("CMC_API_KEY",""), "Accept": "application/json"}

def _fmt(val):
    if not val: return "N/A"
    if val >= 1e12: return f"${val/1e12:.2f}T"
    elif val >= 1e9: return f"${val/1e9:.2f}B"
    elif val >= 1e6: return f"${val/1e6:.2f}M"
    return f"${val:,.0f}"

def get_news():
    try:
        r = requests.get(
            "https://api.coinmarketcap.com/content/v3/news",
            params={"coins":"1,1027","page":1,"size":8},
            headers={"User-Agent":"Mozilla/5.0"},
            timeout=10
        )
        if r.status_code == 200:
            items = r.json().get("data",{}).get("news",[])
            return [i.get("meta",{}).get("title","") for i in items[:8]]
    except:
        pass
    return ["No news available"]

def fetch_cmc_data(symbol="BTC"):
    print(f"  Fetching CMC for {symbol}...")
    news = get_news()
    result = {
        "news": news,
        "quote_formatted": {},
        "global": {},
        "trending": "N/A",
        "gainers": "N/A",
        "losers": "N/A",
        "has_api_key": _has_key()
    }
    if not _has_key():
        return result
    try:
        r = requests.get(
            "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest",
            headers=_headers(),
            params={"symbol":symbol,"convert":"USD"},
            timeout=10
        )
        d = r.json()["data"][symbol]["quote"]["USD"]
        info = r.json()["data"][symbol]
        result["quote_formatted"] = {
            "cmc_rank": info.get("cmc_rank"),
            "market_cap": _fmt(d.get("market_cap")),
            "dominance": f"{d.get('market_cap_dominance','N/A')}%",
            "volume_24h": _fmt(d.get("volume_24h")),
            "change_1h": f"{round(d.get('percent_change_1h',0),2)}%",
            "change_24h": f"{round(d.get('percent_change_24h',0),2)}%",
            "change_7d": f"{round(d.get('percent_change_7d',0),2)}%",
            "change_30d": f"{round(d.get('percent_change_30d',0),2)}%",
        }
    except Exception as e:
        print(f"  CMC quote error: {e}")
    try:
        r = requests.get(
            "https://pro-api.coinmarketcap.com/v1/global-metrics/quotes/latest",
            headers=_headers(),
            params={"convert":"USD"},
            timeout=10
        )
        d = r.json()["data"]
        q = d["quote"]["USD"]
        result["global"] = {
            "total_market_cap": _fmt(q.get("total_market_cap")),
            "total_volume_24h": _fmt(q.get("total_volume_24h")),
            "btc_dominance": f"{round(d.get('btc_dominance',0),2)}%",
            "eth_dominance": f"{round(d.get('eth_dominance',0),2)}%",
            "market_cap_change": f"{round(q.get('total_market_cap_yesterday_percentage_change',0),2)}%",
            "defi_market_cap": _fmt(q.get("defi_market_cap")),
        }
    except Exception as e:
        print(f"  CMC global error: {e}")
    return result
