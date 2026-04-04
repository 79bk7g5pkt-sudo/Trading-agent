import asyncio
import argparse
import json
import time
import requests
import os
import threading
from datetime import datetime
from core.agent import ClaudeTradingAgent
from data.binance_feed import fetch_market_data

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
agent = None
running = True
current_mode = "live"
last_market_data = {}
last_decision = {}

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

def format_decision(decision, market_data):
    action = decision.get("action", "HOLD")
    price = market_data.get("price", 0)
    symbol = market_data.get("symbol", "BTC/USDT")
    confidence = decision.get("confidence", 0)
    stop_loss = decision.get("stop_loss", 0)
    take_profit = decision.get("take_profit", 0)
    risk = decision.get("risk_level", "N/A")
    reasoning = decision.get("reasoning", "N/A")
    whale = decision.get("whale_impact", "N/A")
    news = decision.get("news_impact", "N/A")
    rsi = market_data.get("indicators", {}).get("rsi", "N/A")
    mode = decision.get("mode", "paper").upper()
    return (
        "CLAUDE TRADING BOT [" + mode + "]\n"
        "ACTION: " + action + "\n"
        + symbol + ": $" + str(round(price, 2)) + "\n"
        "Confidence: " + str(confidence) + "%\n"
        "Risk: " + str(risk) + "\n"
        "Take Profit: $" + str(take_profit) + "\n"
        "Stop Loss: $" + str(stop_loss) + "\n"
        "RSI: " + str(rsi) + "\n"
        "Whale: " + str(whale) + "\n"
        "News: " + str(news) + "\n"
        "Reason: " + str(reasoning)[:200] + "\n"
        "Time: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

def get_balance():
    try:
        from binance.client import Client
        client = Client(
            os.environ.get("BINANCE_API_KEY"),
            os.environ.get("BINANCE_SECRET_KEY")
        )
        usdt = float(client.get_asset_balance(asset="USDT")["free"])
        btc = float(client.get_asset_balance(asset="BTC")["free"])
        btc_price = last_market_data.get("price", 0)
        total = usdt + (btc * btc_price)
        return (
            "BINANCE BALANCE\n"
            "USDT: $" + str(round(usdt, 2)) + "\n"
            "BTC: " + str(round(btc, 6)) + "\n"
            "BTC Value: $" + str(round(btc * btc_price, 2)) + "\n"
            "Total: $" + str(round(total, 2))
        )
    except Exception as e:
        return "Balance error: " + str(e)

def handle_command(text):
    global running, current_mode, agent
    text = text.strip().lower()

    if text in ["/start", "/help"]:
        send_telegram(
            "CLAUDE TRADING BOT COMMANDS\n"
            "/status - Current market analysis\n"
            "/balance - Check Binance balance\n"
            "/buy - Force BUY order now\n"
            "/sell - Force SELL order now\n"
            "/stop - Stop the bot\n"
            "/start_bot - Resume the bot\n"
            "/mode_live - Switch to live trading\n"
            "/mode_paper - Switch to paper trading\n"
            "/portfolio - View paper portfolio"
        )

    elif text == "/status":
        if last_decision and last_market_data:
            send_telegram(format_decision(last_decision, last_market_data))
        else:
            send_telegram("No analysis yet - waiting for first cycle")

    elif text == "/balance":
        send_telegram(get_balance())

    elif text == "/buy":
        send_telegram("Forcing BUY order...")
        try:
            forced = {
                "action": "BUY",
                "confidence": 100,
                "position_size_pct": 5,
                "stop_loss": last_market_data.get("price", 0) * 0.97,
                "take_profit": last_market_data.get("price", 0) * 1.05,
                "reasoning": "Manual BUY via Telegram",
                "mode": current_mode,
                "symbol": last_market_data.get("symbol", "BTC/USDT")
            }
            result = agent.execute_decision(forced, last_market_data)
            send_telegram("BUY executed: " + str(result))
        except Exception as e:
            send_telegram("BUY error: " + str(e))

    elif text == "/sell":
        send_telegram("Forcing SELL order...")
        try:
            forced = {
                "action": "SELL",
                "confidence": 100,
                "position_size_pct": 100,
                "stop_loss": 0,
                "take_profit": 0,
                "reasoning": "Manual SELL via Telegram",
                "mode": current_mode,
                "symbol": last_market_data.get("symbol", "BTC/USDT")
            }
            result = agent.execute_decision(forced, last_market_data)
            send_telegram("SELL executed: " + str(result))
        except Exception as e:
            send_telegram("SELL error: " + str(e))

    elif text == "/stop":
        running = False
        send_telegram("Bot stopped")

    elif text == "/start_bot":
        running = True
        send_telegram("Bot resumed")

    elif text == "/mode_live":
        current_mode = "live"
        if agent:
            agent.set_mode("live")
        send_telegram("Switched to LIVE mode")

    elif text == "/mode_paper":
        current_mode = "paper"
        if agent:
            agent.set_mode("paper")
        send_telegram("Switched to PAPER mode")

    elif text == "/portfolio":
        if agent:
            p = agent.get_portfolio_summary()
            send_telegram(
                "PAPER PORTFOLIO\n"
                "USDT: $" + str(round(p["usdt_balance"], 2)) + "\n"
                "Positions: " + str(p["positions"]) + "\n"
                "Total Trades: " + str(p["total_trades"])
            )
        else:
            send_telegram("Agent not started yet")

    elif text == "/pnl":
        try:
            from binance.client import Client
            c = Client(os.environ.get("BINANCE_API_KEY"), os.environ.get("BINANCE_SECRET_KEY"))
            eth = c.get_my_trades(symbol="ETHUSDT", limit=50)
            btc = c.get_my_trades(symbol="BTCUSDT", limit=50)
            xrp = c.get_my_trades(symbol="XRPUSDT", limit=50)
            all_trades = eth + btc + xrp
            bought = sum(float(t["quoteQty"]) for t in all_trades if t["isBuyer"])
            sold = sum(float(t["quoteQty"]) for t in all_trades if not t["isBuyer"])
            fees = sum(float(t["commission"]) for t in all_trades if t["commissionAsset"] == "USDT")
            pnl = sold - bought - fees
            send_telegram("PNL REPORT\nBought: $" + str(round(bought,2)) + "\nSold: $" + str(round(sold,2)) + "\nFees: $" + str(round(fees,2)) + "\nNet PnL: $" + str(round(pnl,2)) + "\nReturn: " + str(round(pnl/bought*100,2)) + "%")
        except Exception as e:
            send_telegram("PnL error: " + str(e))

    
        else:
            send_telegram("Agent not started yet")

def telegram_listener():
    last_update_id = 0
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TOKEN}/getUpdates",
                params={"offset": last_update_id + 1, "timeout": 30},
                timeout=35
            )
            updates = r.json().get("result", [])
            for update in updates:
                last_update_id = update["update_id"]
                msg = update.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text = msg.get("text", "")
                if chat_id == str(CHAT_ID) and text:
                    print(f"Telegram command: {text}")
                    handle_command(text)
        except Exception as e:
            print(f"Listener error: {e}")
            time.sleep(5)

def save_state(decision, market_data):
    state = {
        "last_updated": datetime.now().isoformat(),
        "market": {
            "symbol": market_data.get("symbol"),
            "price": market_data.get("price"),
            "indicators": market_data.get("indicators"),
            "sentiment": market_data.get("sentiment"),
            "orderbook": market_data.get("orderbook"),
            "cmc": market_data.get("cmc", {}),
            "whales": market_data.get("whales", {})
        },
        "last_decision": decision,
        "portfolio": agent.get_portfolio_summary() if agent else {}
    }
    with open("agent_state.json", "w") as f:
        json.dump(state, f, indent=2)

async def run(symbol="BTCUSDT", interval="15m", mode="paper", max_cycles=None):
    global agent, running, current_mode, last_market_data, last_decision
    current_mode = mode
    agent = ClaudeTradingAgent(mode=mode)
    intervals = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
    wait = intervals.get(interval, 900)
    if not max_cycles:
        listener = threading.Thread(target=telegram_listener, daemon=True)
        listener.start()



    send_telegram(
        "Bot started\n"
        "Symbol: " + symbol + "\n"
        "Mode: " + mode.upper() + "\n"
        "Interval: " + interval + "\n"
        "Send /help for commands"
    )
    cycle = 0
    while running:
        cycle += 1
        if max_cycles and cycle > max_cycles:
            break
        print(f"\n[Cycle {cycle}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        try:
            market_data = fetch_market_data(symbol, interval)
            last_market_data = market_data
            price = market_data["price"]
            rsi = market_data["indicators"]["rsi"]
            print(f"Price: ${price:,.4f} | RSI: {rsi}")
            print("Consulting Claude AI...")
            decision = await agent.analyze_and_decide(market_data)
            last_decision = decision
            action = decision.get("action", "HOLD")
            confidence = decision.get("confidence", 0)
            print(f"Decision: {action} | Confidence: {confidence}%")
            send_telegram(format_decision(decision, market_data))
            result = agent.execute_decision(decision, market_data)
            print(f"Result: {result}")
            if result.get("status") == "executed_live":
                send_telegram(
                    "TRADE PLACED on Binance\n"
                    + action + " " + symbol + " @ $" + str(round(price, 2))
                )
            save_state(decision, market_data)
        except Exception as e:
            print(f"Error: {e}")
            send_telegram("Error: " + str(e))
        if running and not (max_cycles and cycle >= max_cycles):
            print(f"Next check in {wait // 60} min...")
            time.sleep(wait)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="15m")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cycles", type=int, default=None)
    args = parser.parse_args()
    mode = "live" if args.live else "paper"
    print("Starting in " + mode.upper() + " mode...")
    asyncio.run(run(args.symbol, args.interval, mode, args.cycles))

if __name__ == "__main__":
    main()
