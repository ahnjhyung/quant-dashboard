import os
import sys
import logging
from datetime import datetime
from data_collectors.macro_data_collector import MacroDataCollector
from auto_trading.email_reporter import EmailReporter
from auto_trading.execution_driver import ExecutionDriver
from config import PAPER_TRADING

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("daily_trigger.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("DailyTrigger")

def run_daily_process():
    """
    매일 실행되는 통합 퀀트 프로세스 트리거:
    [권장 스케줄] Google Apps Script 수집기 실행 완료 약 30분~1시간 후 실행
    1. 데이터 수집 보완 (GAS가 채우지 못한 지표 수집 & DB 존재 확인 시 Skip)
    2. 데이터 분석 및 이메일 전송 (Supabase -> Email)
    """
    start_time = datetime.now()
    logger.info(f"=== 통합 퀀트 브리핑 프로세스 시작 ({start_time}) ===")

    try:
        # Step 1: 매크로 데이터 수집 및 DB 최신화
        logger.info("[Step 1] 매크로 데이터 수집 시작...")
        collector = MacroDataCollector()
        collector.run_all()
        logger.info("[Step 1] 데이터 수집 및 DB 적재 완료.")

        # Step 2: 분석 및 이메일 리포트 발송
        logger.info("[Step 2] 이메일 리포트 분석 및 전송 시작...")
        reporter = EmailReporter()
        reporter.send_email()
        logger.info("[Step 2] 이메일 전송 프로세스 종료.")

        # Step 3: 자동 매매 리밸런싱 실행 (Execution Bridge)
        logger.info("[Step 3] 포트폴리오 리밸런싱(자동 매매) 시작...")
        driver = ExecutionDriver(paper_trading=PAPER_TRADING)
        # CDM 3.0 엔진이 적용된 AGA Broad 전략으로 실행
        driver.run_rebalance(strategy_name="AGA Broad (CDM3)")
        logger.info("[Step 3] 자동 매매 루프 종료.")

        end_time = datetime.now()
        duration = end_time - start_time
        logger.info(f"=== 모든 프로세스 성공적으로 완료 (소요시간: {duration}) ===")

    except Exception as e:
        logger.error(f"!!! [CRITICAL ERROR] 통합 프로세스 도중 오류 발생: {e}")
        # 오류 발생 시에도 최소한의 로그는 남김
        raise

if __name__ == "__main__":
    # 윈도우 인코딩 대응 (이모지 및 특수문자 출력 에러 방지)
    try:
        if sys.platform == "win32":
            import os
            os.environ["PYTHONIOENCODING"] = "utf-8"
    except:
        pass

    run_daily_process()
