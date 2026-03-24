import json
import os
from datetime import datetime

log_file = r"d:\재형\재형\금융\투자\투자 프로그램 개발\hft_arb\logs\arb_signals.jsonl"

def analyze():
    if not os.path.exists(log_file):
        print("Log file not found.")
        return

    signals = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                signals.append(json.loads(line))
            except:
                continue

    if not signals:
        print("No signals found.")
        return

    total_count = len(signals)
    avg_ev = sum(s.get("ev_pct", 0) for s in signals) / total_count
    
    # Calculate time range
    timestamps = [s.get("recorded_at", 0) for s in signals]
    min_ts = min(timestamps)
    max_ts = max(timestamps)
    duration_sec = max_ts - min_ts
    
    # Simulated profit calculation (assuming $10,000 per trade)
    # Note: In real HFT, we wouldn't trade 100% of signals due to execution limits, 
    # but this shows the 'opportunity flow'.
    total_gross = sum(s.get("details", {}).get("gross_usd", 0) for s in signals)
    total_cost = sum(s.get("details", {}).get("cost_usd", 0) for s in signals)
    total_net = total_gross - total_cost

    print(f"=== HFT Arb Performance Analysis ===")
    print(f"Analysis Period: {datetime.fromtimestamp(min_ts)} ~ {datetime.fromtimestamp(max_ts)}")
    print(f"Total Signals: {total_count}")
    print(f"Average EV: {avg_ev:.4f}%")
    print(f"Duration: {duration_sec:.2f} seconds")
    
    if duration_sec > 0:
        signals_per_min = (total_count / duration_sec) * 60
        print(f"Signals/min: {signals_per_min:.2f}")
        
        # Extrapolate to Hourly
        hourly_profit = (total_net / duration_sec) * 3600
        print(f"Estimated Hourly Gross Profit: ${total_gross/duration_sec*3600:.2f}")
        print(f"Estimated Hourly Net Profit: ${hourly_profit:.2f}")

if __name__ == "__main__":
    analyze()
