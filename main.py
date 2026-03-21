import asyncio
import argparse
import json
import time
from datetime import datetime
from core.agent import ClaudeTradingAgent
from data.binance_feed import fetch_market_data

def print_decision(decision):
    action = decision.get("action","HOLD")
    print(f"\n{'='*40}")
    print(f"ACTION: {action}")
    print(f"Confidence: {decision.get('confidence',0)}%")
    print(f"Position Size: {decision.get('position_size_pct',0)}%")
    print(f"Stop Loss: ${decision.get('stop_loss','N/A')}")
    print(f"Take Profit: ${decision.get('take_profit','N/A')}")
    print(f"Risk: {decision.get('risk_level','N/A')}")
    print(f"Reasoning: {decision.get('reasoning','N/A')}")
    print(f"Whale Impact: {decision.get('whale_impact','N/A')}")
    print(f"News Impact: {decision.get('news_impact','N/A')}")
    print(f"{'='*40}\n")

def save_state(agent, decision, market_data):
    state = {
        "last_updated": datetime.now().isoformat(),
        "market": {
            "symbol": market_data.get("symbol"),
            "price": market_data.get("price"),
            "indicators": market_data.get("indicators"),
            "sentiment": market_data.get("sentiment"),
            "orderbook": market_data.get("orderbook"),
            "cmc": market_data.get("cmc",{}),
            "whales": market_data.get("whales",{})
        },
        "last_decision": decision,
        "portfolio": agent.get_portfolio_summary()
    }
    with open("agent_state.json","w") as f:
        json.dump(state, f, indent=2)
    print("State saved to agent_state.json")

async def run(symbol="BTCUSDT", interval="1h", mode="paper", max_cycles=None):
    agent = ClaudeTradingAgent(mode=mode)
    intervals = {"1m":60,"5m":300,"15m":900,"1h":3600,"4h":14400,"1d":86400}
    wait = intervals.get(interval, 3600)
    cycle = 0
    print(f"Starting: {symbol} | {interval} | {mode.upper()} mode")
    while True:
        cycle += 1
        if max_cycles and cycle > max_cycles:
            print(f"Completed {max_cycles} cycles")
            break
        print(f"\n[Cycle {cycle}] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        try:
            market_data = fetch_market_data(symbol, interval)
            print(f"Price: ${market_data['price']:,.4f} | RSI: {market_data['indicators']['rsi']}")
            print("Consulting Claude AI...")
            decision = await agent.analyze_and_decide(market_data)
            print_decision(decision)
            result = agent.execute_decision(decision, market_data)
            print(f"Trade result: {result}")
            save_state(agent, decision, market_data)
        except KeyboardInterrupt:
            print("Stopped by user")
            break
        except Exception as e:
            print(f"Error: {e}")
        if not (max_cycles and cycle >= max_cycles):
            print(f"Next check in {wait//60} minutes...")
            time.sleep(wait)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cycles", type=int, default=None)
    args = parser.parse_args()
    mode = "live" if args.live else "paper"
    if mode == "live":
        confirm = input("Type YES to confirm live trading: ")
        if confirm != "YES":
            print("Aborted")
            return
    asyncio.run(run(args.symbol, args.interval, mode, args.cycles))

if __name__ == "__main__":
    main()
