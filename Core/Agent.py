import os
import json
import asyncio
from datetime import datetime
import anthropic

class ClaudeTradingAgent:
    def __init__(self, mode="paper"):
        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        self.mode = mode
        self.model = "claude-sonnet-4-20250514"
        self.conversation_history = []
        self.trade_log = []
        self.portfolio = {"USDT": 10000.0, "positions": {}}
        print(f"Agent started in {mode.upper()} mode")

    def set_mode(self, mode):
        self.mode = mode

    def _format_headlines(self, headlines):
        if not headlines:
            return "  No recent news"
        return "\n".join(f"  - {h}" for h in headlines[:6])

    def _format_whale_txs(self, txs):
        if not txs:
            return "  No large transactions"
        return "\n".join(f"  {tx}" for tx in txs[:6])

    def _format_trade_history(self):
        if not self.trade_log:
            return "  No trades yet"
        return "\n".join(f"  [{t['time']}] {t['action']} {t['qty']} {t['symbol']} @ ${t['price']:.4f}" for t in self.trade_log[-5:])

    def build_market_context(self, market_data):
        symbol = market_data.get("symbol", "UNKNOWN")
        price = market_data.get("price", 0)
        indicators = market_data.get("indicators", {})
        orderbook = market_data.get("orderbook", {})
        sentiment = market_data.get("sentiment", {})
        cmc = market_data.get("cmc", {})
        whales = market_data.get("whales", {})
        portfolio = self.portfolio
        cmc_q = cmc.get("quote_formatted", {})
        cmc_g = cmc.get("global", {})
        mw = whales.get("market_wide", {})
        return f"""
=== MARKET SNAPSHOT [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC] ===
ASSET: {symbol}
PRICE: ${price:,.4f}
--- TECHNICAL INDICATORS ---
RSI: {indicators.get('rsi','N/A')}
MACD: {indicators.get('macd','N/A')}
EMA20: {indicators.get('ema_20','N/A')}
EMA50: {indicators.get('ema_50','N/A')}
BB Upper: {indicators.get('bb_upper','N/A')}
BB Lower: {indicators.get('bb_lower','N/A')}
ATR: {indicators.get('atr','N/A')}
Volume 24h: {indicators.get('volume_24h','N/A')}
--- ORDER BOOK ---
Bid: ${orderbook.get('best_bid','N/A')}
Ask: ${orderbook.get('best_ask','N/A')}
Spread: {orderbook.get('spread_pct','N/A')}%
Buy/Sell Ratio: {orderbook.get('buy_sell_ratio','N/A')}
--- CMC DATA ---
Market Cap: {cmc_q.get('market_cap','N/A')}
Change 24h: {cmc_q.get('change_24h','N/A')}
BTC Dominance: {cmc_g.get('btc_dominance','N/A')}
--- NEWS ---
{self._format_headlines(sentiment.get('headlines',[]))}
--- WHALE ACTIVITY ---
Signal: {whales.get('net_signal','N/A')}
{whales.get('net_signal_detail','N/A')}
{self._format_whale_txs(whales.get('transactions',[]))}
--- PORTFOLIO ---
USDT: ${portfolio['USDT']:,.2f}
Positions: {json.dumps(portfolio.get('positions',{}))}
--- TRADES ---
{self._format_trade_history()}
"""

    async def analyze_and_decide(self, market_data):
        context = self.build_market_context(market_data)
        system = """You are an expert crypto day trader.
Analyze the data and return ONLY a JSON object:
{
  "action": "BUY" or "SELL" or "HOLD",
  "confidence": 0-100,
  "position_size_pct": 0-100,
  "stop_loss": float,
  "take_profit": float,
  "reasoning": "explanation",
  "key_signals": ["s1","s2","s3"],
  "whale_impact": "BULLISH or BEARISH or NEUTRAL",
  "news_impact": "BULLISH or BEARISH or NEUTRAL",
  "risk_level": "LOW or MEDIUM or HIGH",
  "time_horizon": "2-4 hours"
}
Rules: Max 10% risk. BUY only if confidence>=65. SELL only if confidence>=60. Return ONLY JSON."""
        self.conversation_history.append({"role": "user", "content": f"{context}\nYour decision?"})
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1000,
            system=system,
            messages=self.conversation_history
        )
        text = response.content[0].text
        self.conversation_history.append({"role": "assistant", "content": text})
        if len(self.conversation_history) > 40:
            self.conversation_history = self.conversation_history[-40:]
        try:
            clean = text.strip().replace("```json","").replace("```","")
            decision = json.loads(clean)
        except:
            decision = {"action": "HOLD", "confidence": 0, "reasoning": "Parse error"}
        decision["timestamp"] = datetime.now().isoformat()
        decision["symbol"] = market_data.get("symbol")
        decision["mode"] = self.mode
        return decision

    def _live_trade(self, decision, price, symbol):
    try:
        from binance.client import Client
        import os
        client = Client(
            os.environ.get("BINANCE_API_KEY"),
            os.environ.get("BINANCE_SECRET_KEY")
        )
        action = decision["action"]
        size_pct = decision.get("position_size_pct", 5) / 100
        sym = symbol.replace("/", "")
        usdt_balance = float(client.get_asset_balance(asset="USDT")["free"])
        self.portfolio["USDT"] = usdt_balance
        if action == "BUY":
            amount = round(usdt_balance * size_pct, 2)
            if amount < 10:
                return {"status": "skipped", "reason": "Balance too low"}
            order = client.order_market_buy(symbol=sym, quoteOrderQty=amount)
            return {"status": "executed_live", "action": "BUY", "amount": amount, "order_id": order["orderId"]}
        elif action == "SELL":
            asset = sym.replace("USDT", "")
            qty = float(client.get_asset_balance(asset=asset)["free"])
            sell_qty = round(qty * size_pct, 6)
            if sell_qty <= 0:
                return {"status": "skipped", "reason": "No "+asset+" to sell"}
            order = client.order_market_sell(symbol=sym, quantity=sell_qty)
            return {"status": "executed_live", "action": "SELL", "qty": sell_qty, "order_id": order["orderId"]}
        return {"status": "no_trade"}
    except Exception as e:
        return {"status": "error", "reason": str(e)}


    def _paper_trade(self, decision, price, symbol):
        action = decision["action"]
        size_pct = decision.get("position_size_pct", 5) / 100
        base = symbol.replace("/USDT","")
        if action == "BUY":
            spend = self.portfolio["USDT"] * size_pct
            if spend < 10:
                return {"status": "skipped", "reason": "Low balance"}
            qty = spend / price
            self.portfolio["USDT"] -= spend
            if base not in self.portfolio["positions"]:
                self.portfolio["positions"][base] = {"qty": 0, "avg_entry": 0}
            pos = self.portfolio["positions"][base]
            total = pos["qty"] + qty
            pos["avg_entry"] = ((pos["qty"] * pos["avg_entry"]) + (qty * price)) / total
            pos["qty"] = total
            trade = {"time": datetime.now().strftime("%H:%M:%S"), "action": "BUY", "symbol": symbol, "qty": round(qty,6), "price": price}
        elif action == "SELL":
            if base not in self.portfolio["positions"]:
                return {"status": "skipped", "reason": "No position"}
            pos = self.portfolio["positions"][base]
            qty = pos["qty"] * size_pct
            proceeds = qty * price
            pnl = (price - pos["avg_entry"]) * qty
            self.portfolio["USDT"] += proceeds
            pos["qty"] -= qty
            if pos["qty"] < 0.000001:
                del self.portfolio["positions"][base]
            trade = {"time": datetime.now().strftime("%H:%M:%S"), "action": "SELL", "symbol": symbol, "qty": round(qty,6), "price": price, "pnl": round(pnl,2)}
        self.trade_log.append(trade)
        trade["status"] = "executed_paper"
        return trade

    def get_portfolio_summary(self):
        return {"mode": self.mode, "usdt_balance": self.portfolio["USDT"], "positions": self.portfolio["positions"], "total_trades": len(self.trade_log), "trade_log": self.trade_log[-10:]}
    def _live_trade(self, decision, price, symbol):
        try:
            from binance.client import Client
            import os
            client = Client(os.environ.get('BINANCE_API_KEY'), os.environ.get('BINANCE_SECRET_KEY'))
            action = decision['action']
            size_pct = decision.get('position_size_pct', 5) / 100
            sym = symbol.replace('/', '')
            usdt = float(client.get_asset_balance(asset='USDT')['free'])
            self.portfolio['USDT'] = usdt
            if action == 'BUY':
                amount = round(usdt * size_pct, 2)
                if amount < 10:
                    return {'status': 'skipped', 'reason': 'Low balance'}
                order = client.order_market_buy(symbol=sym, quoteOrderQty=amount)
                return {'status': 'executed_live', 'action': 'BUY', 'amount': amount, 'order_id': order['orderId']}
            elif action == 'SELL':
                asset = sym.replace('USDT', '')
                qty = float(client.get_asset_balance(asset=asset)['free'])
                sell_qty = round(qty * size_pct, 6)
                if sell_qty <= 0:
                    return {'status': 'skipped', 'reason': 'No '+asset+' to sell'}
                order = client.order_market_sell(symbol=sym, quantity=sell_qty)
                return {'status': 'executed_live', 'action': 'SELL', 'qty': sell_qty, 'order_id': order['orderId']}
            return {'status': 'no_trade'}
        except Exception as e:
            return {'status': 'error', 'reason': str(e)}
