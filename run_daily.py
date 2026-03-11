"""
데일리 자동화 스케줄러
======================
평일 아침 지정된 시간(08:30)에 노션 리포트와 
이메일 추천 브리핑을 자동으로 실행하는 데몬 스크립트입니다.
"""

import schedule
import time
import datetime
from auto_trading.notion_reporter import NotionReporter
from auto_trading.email_reporter import EmailReporter

def job_morning_briefing():
    """아침 브리핑 (노션 업데이트 및 메일 발송)"""
    now = datetime.datetime.now()
    # 주말(토=5, 일=6)에는 실행하지 않도록 처리
    if now.weekday() >= 5:
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] 주말이므로 브리핑을 건너뜁니다.")
        return

    print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] ☀️ 아침 퀀트 브리핑을 시작합니다...")
    
    try:
        # 1. 이메일 전송 (가장 중요)
        print(">> 이메일 리포트 생성 및 발송 중...")
        email_rep = EmailReporter()
        email_rep.send_email()
        print(">> 이메일 발송 완료.")
    except Exception as e:
        print(f"❌ 이메일 리포터 오류: {e}")
        
    try:
        # 2. 노션 대시보드 업데이트
        print(">> 노션 대시보드 리포팅 중...")
        notion_rep = NotionReporter()
        notion_rep.generate_daily_report()
        print(">> 노션 리포팅 완료.")
    except Exception as e:
        print(f"❌ 노션 리포터 오류: {e}")

if __name__ == "__main__":
    print("=== 퀀트 투자 시스템 데일리 스케줄러 시작 ===")
    print("설정된 스케줄: 평일 매일 아침 08:30 실행")
    
    # schedule 등록
    schedule.every().day.at("08:30").do(job_morning_briefing)
    
    # 즉시 1회 테스트 런 (원할 경우 주석 해제)
    # print("[테스트] 즉시 1회 실행합니다...")
    # job_morning_briefing()
    
    # 무한 루프
    while True:
        try:
            schedule.run_pending()
            time.sleep(60) # 1분마다 체크
        except KeyboardInterrupt:
            print("\n스케줄러를 종료합니다.")
            break
        except Exception as e:
            print(f"알 수 없는 오류 발생: {e}")
            time.sleep(60)
