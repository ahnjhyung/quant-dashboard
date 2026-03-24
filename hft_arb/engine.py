"""
engine.py
=========
HFT 차익거래 엔진 메인 루프 (100% 몰빵 모드)
"""
import time
from hft_arb.core.state_machine import StateMachine, ArbState
from hft_arb.core.validator import TradeValidator
from hft_arb.market.kimchi_feed import KimchiPremiumFeed
from hft_arb.execution.order_manager import AtomicOrderManager
from hft_arb.monitoring.risk_manager import RiskManager

class ArbEngine:
    def __init__(self, paper_trading: bool = True):
        self.sm = StateMachine()
        self.validator = TradeValidator(min_spread=0.5)
        self.feed = KimchiPremiumFeed()
        self.executor = AtomicOrderManager(paper_trading=paper_trading)
        self.risk = RiskManager(daily_loss_limit=-3.0)
        self.running = False
        self.balance = 1000000.0

    def run(self):
        print("[ENGINE] HFT Arbitrage Engine Started (100% Allocation Mode)")
        self.running = True
        while self.running:
            try:
                self.cycle()
            except Exception as e:
                print(f"[CORE ERROR] {e}")
                self.sm.transition_to(ArbState.HALTED)
                self.running = False
            time.sleep(1)

    def cycle(self):
        self.sm.transition_to(ArbState.SCANNING)
        prices = self.feed.fetch_prices()
        if not prices: return

        best_symbol = None
        best_premium = -99.0
        for s, data in prices.items():
            if data['premium'] > best_premium:
                best_premium = data['premium']
                best_symbol = s

        if best_premium >= self.validator.min_spread:
            print(f"[SIGNAL] Found opportunity in {best_symbol}: {best_premium:.2f}%")
            self.sm.transition_to(ArbState.SIGNAL_FOUND, context_update={
                "symbol": best_symbol, "premium": best_premium, "data": prices[best_symbol],
                "timestamp": time.time(), "has_balance": True, "latency": 0.05
            })
            self.sm.transition_to(ArbState.VALIDATING)
            ok, msg = self.validator.validate_pre_trade(self.sm.get_context())
            if ok:
                order_size_krw = self.risk.calculate_order_size(self.balance, best_symbol)
                self.sm.transition_to(ArbState.EXECUTING_LEG1)
                res1 = self.executor.execute_leg1(f"{best_symbol}USDT", "SELL", 0.1, prices[best_symbol]['binance'])
                if res1['status'] == "FILLED":
                    self.sm.transition_to(ArbState.LEG1_FILLED)
                    self.sm.transition_to(ArbState.EXECUTING_LEG2)
                    res2 = self.executor.execute_leg2(f"KRW-{best_symbol}", "BUY", order_size_krw, prices[best_symbol]['upbit'])
                    if res2['status'] == "FILLED":
                        self.sm.transition_to(ArbState.LEG2_FILLED)
                        print(f"[SUCCESS] Arbitrage Cycle Completed for {best_symbol}!")
                        self.sm.transition_to(ArbState.IDLE)
                        self.sm.clear_context()
                    else:
                        self.sm.transition_to(ArbState.UNWINDING)
                        print("[LEG2 FAIL] Starting Unwind...")
                else:
                    self.sm.transition_to(ArbState.UNWINDING)
                    print("[LEG1 FAIL] Starting Unwind...")
            else:
                print(f"[VALIDATE FAIL] {msg}")
                self.sm.transition_to(ArbState.IDLE)
        else:
            self.sm.transition_to(ArbState.IDLE)

if __name__ == "__main__":
    engine = ArbEngine(paper_trading=True)
    engine.validator.min_spread = 0.1 
    engine.run()
