import os
import time
import requests

EXCHANGES = {"binance","coinbase","kraken","bitfinex","huobi","okx","kucoin","bybit"}

def _key():
    return os.environ.get("WHALE_ALERT_API_KEY","").strip()

def fetch_whale_data(symbol="BTC", min_usd=500000):
    print("  Fetching whale data for "+symbol+"...")
    return {
        "net_signal": "NEUTRAL",
        "net_signal_detail": "Whale data unavailable",
        "transactions": [],
        "total_usd_moved": "0",
        "exchange_inflows": "0",
        "exchange_outflows": "0",
        "bullish_count": 0,
        "bearish_count": 0,
        "transaction_count": 0,
        "market_wide": {
            "all_exchange_inflows": "0",
            "all_exchange_outflows": "0",
            "stablecoin_moves": "0",
            "stablecoin_note": "",
            "total_txs_tracked": 0
        },
        "has_api_key": bool(_key())
    }
