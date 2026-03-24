import json
import os

log_file = r"d:\재형\재형\금융\투자\투자 프로그램 개발\hft_arb\logs\arb_signals.jsonl"

def backtest():
    if not os.path.exists(log_file):
        return

    signals = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                signals.append(json.loads(line))
            except:
                continue

    if not signals:
        return

    capital = 1_000_000  # KRW
    fee_rate = 0.0015    # 0.15% total (Upbit + Binance)
    
    # Simple Strategy: Mean Reversion on KP
    # We enter when KP is below avg, exit when above avg.
    ev_list = [s['ev_pct'] for s in signals]
    avg_ev = sum(ev_list) / len(ev_list)
    
    # Calculate "Tradeable Spread"
    # Number of times KP crosses the mean + threshold
    threshold = 0.05  # 0.05% deviation
    
    pos = 0  # 0: None, 1: Long Premium (Buy Binance/Sell Upbit)
    trades = 0
    total_profit = 0
    
    for i in range(1, len(ev_list)):
        prev_ev = ev_list[i-1]
        curr_ev = ev_list[i]
        
        # Entry: Premium is low (Rebalancing opportunity or Buy Binance)
        if pos == 0 and curr_ev < (avg_ev - threshold):
            pos = 1
            entry_ev = curr_ev
            
        # Exit: Premium is high (Arbitrage opportunity or Sell Upbit)
        elif pos == 1 and curr_ev > (avg_ev + threshold):
            # Profit = (Exit EV - Entry EV) - Fees
            profit_pct = (curr_ev - entry_ev) - (fee_rate * 100)
            if profit_pct > 0:
                total_profit += (capital * (profit_pct / 100))
                trades += 1
            pos = 0

    duration_min = (signals[-1]['recorded_at'] - signals[0]['recorded_at']) / 60
    
    print(f"=== 4-Minute Backtest Results (Capital: 1,000,000 KRW) ===")
    print(f"Total Trades: {trades}")
    print(f"Net Profit (4m): {total_profit:.2f} KRW ({total_profit/capital*100:.4f}%)")
    
    # Extrapolate to Monthly (30 days, 24/7)
    monthly_multiplier = (60 * 24 * 30) / duration_min
    monthly_profit = total_profit * monthly_multiplier
    
    print(f"Extrapolated Monthly Profit: {monthly_profit:,.2f} KRW")
    print(f"Estimated Monthly ROI: {monthly_profit/capital*100:.2f}%")

if __name__ == "__main__":
    backtest()
