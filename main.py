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
    emoji = "🟢" if action == "BUY" else "🔴" if action == "SELL" else "⏸"
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
    return f"""🤖 <b>CLAUDE TRADING BOT</b> [{mode}]
━━━━━━━━━━━━━━━━━━
{emoji} <b>ACTION: {action}</b>
💰 {symbol}: ${price:,.2f}
📊 Confidence: {confidence}%
⚠️ Risk: {risk}
━━━━━━━━━━━━━━━━━━
🎯 Take Profit: ${take_profit:,}
🛑 Stop Loss: ${stop_loss:,}
📈 RSI: {rsi}
🐋 Whale: {whale}
📰 News: {news}
━━━━━━━━━━━━━━━━━━
💭 <i>{str(reasoning)[:200]}</i>
━━━━━━━━━━━━━━━━━━
🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

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
        return f"""💼 <b>BINANCE BALANCE</b>
━━━━━━━━━━━━━━━━━━
💵 USDT: ${usdt:,.2f}
₿ BTC: {btc:.6f}
💰 BTC Value: ${btc*btc_price:,.2f}
━━━━━━━━━━━━━━━━━━
📊 Total: ${total:,.2f}"""
    except Exception as e:
        return f"Balance error: {e}"

def handle_command(text):
    global running, current_mode, agent
    text = text.strip().lower()

    if text == "/start" or text == "/help":
        send_telegram("""🤖 <b>CLAUDE TRADING BOT COMMANDS</b>
━━━━━━━━━━━━━━━━━━
/status - Current market analysis
/balance - Check Binance balance
/buy - Force BUY order now
/sell - Force SELL order now
/stop - Stop the bot
/start_bot - Resume the bot
/mode_live - Switch to live trading
/mode_paper - Switch to paper trading
/portfolio - View paper portfolio
━━━━━━━━━━━━━━━━━━
Bot is running 24/7 on your VPS""")

    elif text == "/status":
        if last_decision and last_market_data:
            send_telegram(format_decision(last_decision, last_market_data))
        else:
            send_telegram("No analysis yet — waiting for first cycle")

    elif text == "/balance":
        send_telegram(get_balance())

    elif text == "/buy":
        send_telegram("⚡ Forcing BUY order...")
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
            send_telegram(f"BUY executed: {json.dumps(result)}")
        except Exception as e:
            send_telegram(f"BUY error: {e}")

    elif text == "/sell":
        send_telegram("⚡ Forcing SELL order...")
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
            send_telegram(f"SELL executed: {json.dumps(result)}")
        except Exception as e:
            send_telegram(f"SELL error: {e}")

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
                        send_telegram("PAPER PORTFOLIO - USDT: " + str(round(p["usdt_balance"],2)) + " Trades: " + str(p["total_trades"]))

USDT: ${p['usdt_balance']:,.2f}
Positions: {json​​​​​​​​​​​​​​​​
