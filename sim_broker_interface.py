# sim_broker_interface.py
# This file adapts your bot's calls to use the MockTradeStationBroker
# instead of making real API calls.

def sim_place_ts_order(mock_broker_instance, symbol, side, qty, stop_price=None, limit_price=None):
    action = "BUY" if side.lower() == "buy" else "SELL"
    order_data = {
        "AccountID": "SIM_ACCOUNT",
        "Symbol": symbol,
        "Quantity": qty,
        "TradeAction": action,
        "OrderType": "Market",
        "TimeInForce": "GTC",
        "Route": "Intelligent",
        "IsBrackets": True,
        "Orders": [
            {"TradeAction": "SELL" if action == "BUY" else "BUY", "OrderType": "Limit", "Quantity": qty, "LimitPrice": limit_price, "TimeInForce": "GTC"},
            {"TradeAction": "SELL" if action == "BUY" else "BUY", "OrderType": "StopMarket", "Quantity": qty, "StopPrice": stop_price, "TimeInForce": "GTC"}
        ]
    }
    return mock_broker_instance.place_order(order_data)

def sim_get_open_position(mock_broker_instance, symbol):
    positions_response = mock_broker_instance.get_open_positions(account_id="SIM_ACCOUNT")
    for pos in positions_response.get("Positions", []):
        if pos["Symbol"].upper() == symbol.upper():
            return {
                "symbol": symbol,
                "qty": abs(pos["Quantity"]),
                "side": "buy" if pos["Quantity"] > 0 else "sell",
                "entry_price": pos["PricePaid"]
            }
    return None

def sim_close_position(mock_broker_instance, symbol, qty, side):
    return mock_broker_instance.close_position(symbol, qty, side)

def sim_apply_trailing_stop(mock_broker_instance, symbol, entry_price, trail_amount, direction, qty, check_interval_sec):
    quote = mock_broker_instance.get_quote(symbol)
    if "Last" not in quote:
        print(f"[{mock_broker_instance.current_sim_time}] Error getting quote for trailing stop: {quote.get('error', 'Unknown')}")
        return

    last_price = quote["Last"]

    if direction == "buy":
        position = sim_get_open_position(mock_broker_instance, symbol)
        if position:
            current_trail_entry = position["entry_price"]
            if last_price <= current_trail_entry:
                print(f"[{mock_broker_instance.current_sim_time}] 🔻 Sim Exiting BUY: {symbol} @ {last_price:.2f} (Trailed to {current_trail_entry:.2f})")
                return sim_close_position(mock_broker_instance, symbol, qty, "buy")
        else:
             print(f"[{mock_broker_instance.current_sim_time}] No position to trail for {symbol}")

    else:
        position = sim_get_open_position(mock_broker_instance, symbol)
        if position:
            current_trail_entry = position["entry_price"]
            if last_price >= current_trail_entry:
                print(f"[{mock_broker_instance.current_sim_time}] 🔺 Sim Exiting SELL: {symbol} @ {last_price:.2f} (Trailed to {current_trail_entry:.2f})")
                return sim_close_position(mock_broker_instance, symbol, qty, "sell")
        else:
             print(f"[{mock_broker_instance.current_sim_time}] No position to trail for {symbol}")
