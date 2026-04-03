import requests
import os
import asyncio
import json
from datetime import datetime
from binance.client import Client
import math

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

HALAL_COINS = [
    "BTC","ETH","BNB","SOL","ADA","DOT","AVAX","ATOM","ALGO","NEAR",
    "FTM","ONE","EGLD","ROSE","HBAR","XDC","IOTA","QTUM","WAVES","ICX",
    "ZIL","ONT","NEO","VET","EOS","TRX","XTZ","THETA","FIL","ICP",
    "XRP","XLM","NANO","BCH","LTC","DASH",
    "LINK","GRT","BAT","ZRX","ENJ","MANA","SAND","AXS","GALA","IMX",
    "CHZ","FLOW","AUDIO","LRC","SKL","STORJ","OCEAN","ANKR","CKB","RVN",
    "DGB","ARDR","STEEM","HIVE",
    "UNI","SUSHI","CRV","SNX","YFI","COMP","MKR","AAVE","1INCH",
    "MATIC","OP","ARB","BOBA","CELR",
    "SLP","ALICE","TLM","HERO","SKILL","TOWER",
    "FET","NMR","AGIX","RNDR",
    "WAN","ARPA","CTSI","BAND","API3","UMA","BAL","PERP"
]

def send_telegram(message):
    if not TOKEN or not CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        print(f"Telegram error: {e}")

def get_whale_coins():
    print("Scanning CoinGecko for whale activity...")
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "volume_desc",
            "per_page": 50,
            "page": 1,
            "sparkline": False,
            "price_change_percentage": "24h"
        }
        r = requests.get(url, params=params, timeout=15)
        coins = r.json()
        whale_candidates = []
        for coin in coins:
            volume = coin.get("total_volume", 0)
            price_change = coin.get("price_change_percentage_24h", 0)
            market_cap = coin.get("market_cap", 0)
            symbol = coin.get("symbol", "").upper()
            name = coin.get("name", "")
            price = coin.get("current_price", 0)
            if market_cap == 0:
                continue
            volume_to_mcap = volume / market_cap
            if (volume_to_mcap > 0.15 and
    0 < price_change < 8 and
    volume > 10000000 and
    symbol in HALAL_COINS):
                whale_candidates.append({
                    "symbol": symbol,
                    "name": name,
                    "price": price,
                    "volume": volume,
                    "market_cap": market_cap,
                    "price_change_24h": price_change,
                    "volume_to_mcap": round(volume_to_mcap, 3)
                })
        whale_candidates.sort(key=lambda x: x["volume_to_mcap"], reverse=True)
        return whale_candidates[:5]
    except Exception as e:
        print(f"CoinGecko error: {e}")
        return []

def check_binance_available(symbol):
    try:
        client = Client(
            os.environ.get("BINANCE_API_KEY"),
            os.environ.get("BINANCE_SECRET_KEY")
        )
        info = client.get_symbol_info(symbol + "USDT")
        return info is not None
    except:
        return False

async def analyze_whale_coin(coin):
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        prompt = f"""Analyze this coin for whale accumulation:

Coin: {coin['name']} ({coin['symbol']})
Price: ${coin['price']}
24h Volume: ${coin['volume']:,.0f}
Market Cap: ${coin['market_cap']:,.0f}
Volume/MCap Ratio: {coin['volume_to_mcap']} (high = whale activity)
24h Price Change: {coin['price_change_24h']}%

High volume relative to market cap suggests large players are accumulating.
Should we BUY this coin expecting significant increase?

Return ONLY JSON:
{{
    "action": "BUY" or "SKIP",
    "confidence": 0-100,
    "reasoning": "brief explanation",
    "take_profit_pct": 10-100,
    "stop_loss_pct": 5-15,
    "risk_level": "LOW/MEDIUM/HIGH"
}}"""
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        print(f"Claude error: {e}")
        return {"action": "SKIP", "confidence": 0, "reasoning": str(e)}

def place_buy_with_oco(symbol, usdt_amount, take_profit_pct, stop_loss_pct):
    try:
        client = Client(
            os.environ.get("BINANCE_API_KEY"),
            os.environ.get("BINANCE_SECRET_KEY")
        )
        buy_order = client.order_market_buy(symbol=symbol+"USDT", quoteOrderQty=usdt_amount)
        filled_qty = float(buy_order["executedQty"])
        filled_price = float(buy_order["cummulativeQuoteQty"]) / filled_qty
        info = client.get_symbol_info(symbol+"USDT")
        lot = next(f for f in info["filters"] if f["filterType"] == "LOT_SIZE")
        price_filter = next(f for f in info["filters"] if f["filterType"] == "PRICE_FILTER")
        step = float(lot["stepSize"])
        tick = float(price_filter["tickSize"])
        sell_qty = float("{:.8f}".format(math.floor(filled_qty / step) * step))
        decimals = len(str(tick).rstrip("0").split(".")[-1])
        tp_price = round(round(filled_price * (1 + take_profit_pct/100) / tick) * tick, decimals)
        sl_price = round(round(filled_price * (1 - stop_loss_pct/100) / tick) * tick, decimals)
        sl_limit = round(round(sl_price * 0.99 / tick) * tick, decimals)
        oco = client.create_oco_order(
            symbol=symbol+"USDT",
            side="SELL",
            quantity="{:.8f}".format(sell_qty),
            aboveType="LIMIT_MAKER",
            abovePrice="{:.{}f}".format(tp_price, decimals),
            belowType="STOP_LOSS_LIMIT",
            belowStopPrice="{:.{}f}".format(sl_price, decimals),
            belowPrice="{:.{}f}".format(sl_limit, decimals),
            belowTimeInForce="GTC"
        )
        return {
            "status": "success",
            "buy_price": filled_price,
            "qty": sell_qty,
            "take_profit": tp_price,
            "stop_loss": sl_price,
            "oco_status": oco["listOrderStatus"]
        }
    except Exception as e:
        return {"status": "error", "reason": str(e)}

async def main():
    print(f"\nWhale Scanner - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    send_telegram("WHALE SCANNER STARTING\nScanning for halal coins with whale activity...")

    coins = get_whale_coins()

    if not coins:
        send_telegram("No halal whale activity detected today.")
        return

    report = "WHALE ACTIVITY REPORT\nTop halal coins with unusual volume:\n\n"
    for coin in coins:
        report += coin["symbol"] + ": +" + str(round(coin["price_change_24h"],1)) + "% | Vol/MCap: " + str(coin["volume_to_mcap"]) + "\n"
    send_telegram(report)

    client = Client(os.environ.get("BINANCE_API_KEY"), os.environ.get("BINANCE_SECRET_KEY"))
    usdt = float(client.get_asset_balance(asset="USDT")["free"])
    trade_amount = round(usdt * 0.05, 2)

    if trade_amount < 10:
        send_telegram("USDT balance too low for whale trades.")
        return

    coin = coins[0]
    symbol = coin["symbol"]
    print(f"Analyzing top halal whale coin: {symbol}")

    if not check_binance_available(symbol):
        send_telegram(symbol + " not available on Binance - skipping")
        return

    analysis = await analyze_whale_coin(coin)
    action = analysis.get("action", "SKIP")
    confidence = analysis.get("confidence", 0)
    reasoning = analysis.get("reasoning", "")
    tp_pct = analysis.get("take_profit_pct", 20)
    sl_pct = analysis.get("stop_loss_pct", 10)

    msg = "WHALE COIN ANALYSIS: " + symbol + "\n"
    msg += "Action: " + action + "\n"
    msg += "Confidence: " + str(confidence) + "%\n"
    msg += "Take Profit: +" + str(tp_pct) + "%\n"
    msg += "Stop Loss: -" + str(sl_pct) + "%\n"
    msg += "Reason: " + reasoning[:200]
    send_telegram(msg)

    if action == "BUY" and confidence >= 60:
        print(f"Buying {symbol}...")
        result = place_buy_with_oco(symbol, trade_amount, tp_pct, sl_pct)
        if result["status"] == "success":
            send_telegram(
                "WHALE BUY EXECUTED\n"
                "Coin: " + symbol + "\n"
                "Amount: $" + str(trade_amount) + "\n"
                "Buy Price: $" + str(round(result["buy_price"],4)) + "\n"
                "Take Profit: $" + str(result["take_profit"]) + "\n"
                "Stop Loss: $" + str(result["stop_loss"]) + "\n"
                "OCO: " + result["oco_status"]
            )
        else:
            send_telegram("Buy failed: " + result.get("reason","unknown"))
    else:
        send_telegram("No trade today - " + action + " (" + str(confidence) + "% confidence)")

    send_telegram("Whale scan complete!")

if __name__ == "__main__":
    asyncio.run(main())
