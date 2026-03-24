import time
import json

class RiskManager:
    """
    Handles Risk Management for the HFT Arb system.
    Monitors Kimchi Premium reversal and Liquidity risks.
    """
    def __init__(self, kp_threshold=8.0, reversal_sensitivity=0.5):
        self.kp_threshold = kp_threshold
        self.reversal_sensitivity = reversal_sensitivity
        self.kp_history = []
        
    def check_risk(self, current_kp: float) -> dict:
        """
        returns a risk report dict.
        """
        self.kp_history.append(current_kp)
        if len(self.kp_history) > 60: # Keep last 60 data points
            self.kp_history.pop(0)
            
        report = {
            "status": "NORMAL",
            "action": "NONE",
            "reason": ""
        }
        
        # 1. Extreme Premium Risk
        if current_kp > 10.0:
            report["status"] = "WARNING"
            report["action"] = "HALT_NEW_POSITIONS"
            report["reason"] = f"Extreme KP ({current_kp:.2f}%). High reversal risk."
            
        # 2. Reversal Detection (Sudden drop)
        if len(self.kp_history) > 5:
            recent_avg = sum(self.kp_history[-5:]) / 5
            prev_avg = sum(self.kp_history[:-5]) / len(self.kp_history[:-5]) if len(self.kp_history[:-5]) > 0 else recent_avg
            
            drop = prev_avg - recent_avg
            if drop > self.reversal_sensitivity:
                report["status"] = "CRITICAL"
                report["action"] = "EXECUTE_HEDGE_SHORT"
                report["reason"] = f"Sudden KP Drop detected ({drop:.2f}% drop). Reversal in progress."

        return report

if __name__ == "__main__":
    # Test case
    rm = RiskManager()
    print("Simulating steady high premium...")
    for _ in range(10): rm.check_risk(9.5)
    
    print("Simulating sudden crash (9.5% -> 8.0%)...")
    report = rm.check_risk(8.0)
    print(f"Risk Report: {json.dumps(report, indent=2)}")
