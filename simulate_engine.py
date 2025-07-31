import time
import uuid
import json

class MockTradeStationBroker:
    def __init__(self, initial_balance=100000.0):
        self.balance = initial_balance
        self.current_positions = {}  # {symbol: {"qty": X, "side": "buy/sell", "entry_price": Y, "open_pnl": 0.0}}
        self.order_history = []
        self.simulated_quotes = {} # {symbol: latest_price}
        self.current_sim_time = None # To track simulation time

    def set_sim_time(self, sim_time):
        """Sets the current simulation time for logging."""
        self.current_sim_time = sim_time

    def update_quote(self, symbol, price):
        """Updates the internal simulated price for a symbol."""
        self.simulated_quotes[symbol] = price
        # Update open PnL for active positions
        if symbol in self.current_positions:
            pos = self.current_positions[symbol]
            if pos["side"] == "buy":
                pos["open_pnl"] = (price - pos["entry_price"]) * pos["qty"]
            else: # sell
                pos["open_pnl"] = (pos["entry_price"] - price) * pos["qty"]

    def get_quote(self, symbol):
        """Mocks GET /data/quote/{symbol}"""
        if symbol not in self.simulated_quotes:
            print(f"[{self.current_sim_time}] ERROR: No simulated quote for {symbol}")
            return {"error": "No quote available"}
        return {"Last": self.simulated_quotes[symbol]}

    def get_open_positions(self, account_id): # account_id is ignored in mock
        """Mocks GET /accounts/{ACCOUNT_ID}/positions"""
        # Convert internal format to TradeStation API-like format
        ts_positions = []
        for symbol, pos_data in self.current_positions.items():
            ts_positions.append({
                "Symbol": symbol,
                "Quantity": pos_data["qty"] if pos_data["side"] == "buy" else -pos_data["qty"],
                "PricePaid": pos_data["entry_price"],
                "MarketValue": pos_data["qty"] * self.simulated_quotes.get(symbol, pos_data["entry_price"]),
                "UnrealizedProfitLoss": pos_data["open_pnl"]
            })
        return {"Positions": ts_positions}

    def place_order(self, order_data):
        """Mocks POST /orderexecution/orderrequests (for market entry)"""
        symbol = order_data["Symbol"]
        qty = order_data["Quantity"]
        trade_action = order_data["TradeAction"]
        order_type = order_data["OrderType"] # Should be "Market" for entry in this simplified mock

        if order_type != "Market":
            print(f"[{self.current_sim_time}] Mock Broker: Only Market orders supported for entry simulation. Received {order_type}")
            return {"status": "error", "message": "Unsupported order type for entry"}

        current_price = self.simulated_quotes.get(symbol)
        if current_price is None:
            return {"status": "error", "message": f"[{self.current_sim_time}] No current price for {symbol} to place order"}

        order_id = str(uuid.uuid4())

        # Simulate cost/revenue at market price
        if trade_action == "BUY":
            cost = qty * current_price
            if self.balance < cost:
                print(f"[{self.current_sim_time}] 🚫 REJECTED: Insufficient funds for BUY {qty} {symbol} @ {current_price:.2f}. Balance: {self.balance:.2f}")
                return {"status": "rejected", "message": "Insufficient funds"}
            self.balance -= cost
            self.current_positions[symbol] = {
                "qty": qty,
                "side": "buy",
                "entry_price": current_price,
                "open_pnl": 0.0 # PnL starts at 0
            }
        elif trade_action == "SELL": # Assuming short selling to open
            revenue = qty * current_price
            self.balance += revenue # Funds received from short sale
            self.current_positions[symbol] = {
                "qty": qty,
                "side": "sell",
                "entry_price": current_price, # This is the price you "sold" at to open the short
                "open_pnl": 0.0
            }
        else:
            return {"status": "error", "message": f"[{self.current_sim_time}] Invalid TradeAction: {trade_action}"}

        self.order_history.append({
            "order_id": order_id,
            "type": "entry",
            "symbol": symbol,
            "qty": qty,
            "action": trade_action,
            "price": current_price,
            "timestamp": self.current_sim_time,
            "status": "filled"
        })
        print(f"[{self.current_sim_time}] 📈 MOCK ORDER FILLED: {trade_action} {qty} {symbol} @ {current_price:.2f} | Balance: {self.balance:.2f}")
        return {"status": "submitted", "response": {"OrderID": order_id, "Status": "Filled"}}

    def close_position(self, symbol, qty, side):
        """Mocks closing a position via market order (used by Sentinel)"""
        if symbol not in self.current_positions:
            print(f"[{self.current_sim_time}] ERROR: Attempted to close {symbol} but no open position.")
            return {"status": "error", "message": f"No open position for {symbol}"}

        pos = self.current_positions[symbol]
        if pos["qty"] < qty:
            print(f"[{self.current_sim_time}] ERROR: Attempting to close more quantity ({qty}) than open position ({pos['qty']}) for {symbol}")
            return {"status": "error", "message": "Attempting to close more than open position"}

        current_price = self.simulated_quotes.get(symbol)
        if current_price is None:
            return {"status": "error", "message": f"[{self.current_sim_time}] No current price for {symbol} to close position"}

        order_id = str(uuid.uuid4())
        exit_value = qty * current_price

        # Calculate realized PnL
        realized_pnl = 0.0
        if pos["side"] == "buy": # Closing a long position (selling)
            realized_pnl = (current_price - pos["entry_price"]) * qty
            self.balance += exit_value
        elif pos["side"] == "sell": # Closing a short position (buying back)
            realized_pnl = (pos["entry_price"] - current_price) * qty
            self.balance -= exit_value # Pay to buy back
            self.balance += (pos["entry_price"] * qty) # Initial short sale funds

        self.balance += realized_pnl # Add the calculated PnL to balance

        # Update position quantity or remove if fully closed
        if pos["qty"] == qty:
            del self.current_positions[symbol]
        else:
            pos["qty"] -= qty

        self.order_history.append({
            "order_id": order_id,
            "type": "exit",
            "symbol": symbol,
            "qty": qty,
            "action": "SELL" if side == "buy" else "BUY",
            "price": current_price,
            "timestamp": self.current_sim_time,
            "status": "filled",
            "pnl": realized_pnl
        })
        print(f"[{self.current_sim_time}] 💸 MOCK POSITION CLOSED: {symbol} | Realized PnL: {realized_pnl:.2f} | New Balance: {self.balance:.2f}")
        return {"status": "submitted", "response": {"OrderID": order_id, "Status": "Filled"}}

    def get_balance(self):
        return self.balance

    def get_order_history(self):
        return self.order_history

    def get_net_pnl(self):
        """Calculates total PnL from closed trades + open PnL."""
        closed_pnl = sum(trade["pnl"] for trade in self.order_history if trade["type"] == "exit")
        open_pnl = sum(pos["open_pnl"] for pos in self.current_positions.values())
        return closed_pnl + open_pnl
