# Phase 13: Slippage guard and entry confirmation logic
def check_slippage(expected_price, actual_price):
    slippage = abs(actual_price - expected_price) / expected_price
    return slippage <= 0.01  # 1% slippage threshold
