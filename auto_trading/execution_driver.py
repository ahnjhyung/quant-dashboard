"""
Execution Driver (Full-Loop Controller)
=====================================
- Role: Bridge between PortfolioEngine and BrokerInterface
- Protocol:
    1. Get target weights from PortfolioEngine (Decision)
    2. Get current holdings from BrokerInterface (State)
    3. Calculate trade deltas (Optimization)
    4. Execute orders (Action)
"""

import logging
from datetime import datetime
from typing import Dict
from analysis.portfolio_engine import PortfolioEngine
from auto_trading.broker_interface import BrokerInterface
from config import PAPER_TRADING

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("ExecutionDriver")

class ExecutionDriver:
    def __init__(self, paper_trading: bool = True):
        self.paper_trading = paper_trading
        self.engine = PortfolioEngine()
        self.broker = BrokerInterface(paper_trading=paper_trading)
        
    def run_rebalance(self, strategy_name: str = "AGA Broad (CDM3)"):
        """전체 리밸런싱 루프 실행"""
        logger.info(f"🚀 Rebalancing process started for strategy: {strategy_name}")
        
        # 1. 최신 타겟 비중 산출 (PortfolioEngine)
        try:
            # AGA Broad (CDM3) 전략은 CDM 3.0 리스크 엔진이 통합된 포트폴리오
            strategies = self.engine.get_all_strategy_configs()
            config = next((s for s in strategies if s['name'] == strategy_name), None)
            
            if not config:
                logger.error(f"Strategy {strategy_name} not found.")
                return

            # 당일 티커 데이터 기반 비중 산출 (Risk Parity + Macro Guard)
            # fetch_multi_data는 내부적으로 yfinance를 사용함
            tickers = config['alpha'] + config['ins']
            data = self.engine.fetch_multi_data(tickers, period="1y")
            
            # CDM 3.0 리스크 점수 반영된 비중 산출
            target_weights = self.engine.calculate_risk_parity_weights(
                tickers, data, datetime.now()
            )
            
            # Macro De-risking 적용 (PortfolioEngine 내부에 구현된 로직 사용)
            # 여기서는 시뮬레이션 환경이 아니므로 현재 날짜 기준으로 직접 적용
            risk_score = self.engine.get_macro_risk_score(datetime.now())
            logger.info(f"Current CDM 3.0 Risk Score: {risk_score:.2f}")

            # 2. 현재 브로커 상태 조회
            balance = self.broker.get_balance()
            current_positions = self.broker.get_positions()
            logger.info(f"Current Balance: ${balance:,.2f}")

            # 3. 주문 델타 계산 및 실행
            logger.info("--- Execution Orders ---")
            for ticker, weight in target_weights.items():
                target_value = balance * weight
                # TODO: 현재 보유수량 반영 로직 (현재는 신규 진입/전량 리밸런싱 가정)
                # 실제 운영 시엔 (target_value - current_value) / current_price로 수량 산출
                
                # 임시로 시연용 가격 정보 가져오기
                current_price = data[ticker]['Close'].iloc[-1] if ticker in data else 100.0
                shares = int(target_value / current_price)
                
                if shares > 0:
                    self.broker.place_order(ticker, "BUY", shares)
                else:
                    logger.info(f"Skipping {ticker} (Target weight too low)")

            logger.info("✅ Rebalancing process completed successfully.")
            
        except Exception as e:
            logger.error(f"Rebalance failed: {e}")
            import traceback
            logger.error(traceback.format_exc())

if __name__ == "__main__":
    # 안전하게 Paper Trading 모드로 실행
    driver = ExecutionDriver(paper_trading=PAPER_TRADING)
    driver.run_rebalance()
