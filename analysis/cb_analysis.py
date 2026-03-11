"""
전환사채(CB) 리픽싱(전환가액 조정) 분석 엔진
============================================
- DART 공시로부터 전환가액 조정 내역 분석
- 리픽싱 후 주가 하락 방어력 및 반등 기대값(EV) 산출
- 전환사채 희석 물량 및 전환 가능 시기 계산
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from data_collectors.open_dart import OpenDartCollector
from analysis.swing_trading import SwingTradingAnalyzer

class CBRefixingAnalyzer:
    """
    CB 리픽싱 분석기
    
    리픽싱(Refixing)은 주가가 떨어졌을 때 전환가도 같이 낮춰주는 조항입니다.
    바닥권에서 리픽싱이 완료된 종목은 '안전마진'이 확보된 것으로 간주합니다.
    """

    def __init__(self):
        self.dart = OpenDartCollector()
        self.swing = SwingTradingAnalyzer()

    def analyze_refixing_opportunity(self, ticker: str, corp_code: str) -> dict:
        """
        특정 종목의 최신 리픽싱 공시 분석 및 기대값 산출
        """
        print(f"🕵️ [{ticker}] CB 리픽싱 기회 분석 중...")
        
        # 1. 최신 리픽싱 공시 조회
        notices = self.dart.get_cb_refixing_notices(corp_code, bgn_de=(datetime.now() - timedelta(days=90)).strftime('%Y%m%d'))
        
        if not notices:
            return {'ticker': ticker, 'signal': 'NONE', 'reason': '최근 90일 내 리픽싱 공시 없음'}

        # 최신 공시 기준
        latest = notices[0]
        report_nm = latest.get('report_nm', '')
        rcept_no = latest.get('rcept_no', '')
        
        # 2. 현재 주가 및 추세 확인
        price_info = self.swing.full_analysis(ticker)
        if 'error' in price_info:
            return {'ticker': ticker, 'error': '주가 데이터 로드 실패'}
            
        current_price = price_info['current_price']
        rsi = price_info['rsi']['value']
        
        # 3. 기대값(EV) 추정
        # QuantAnalyst: 리픽싱 후 주가 반등 확률(승률) 추정 모델 개선
        # 기반 가정: RSI가 낮을수록(과매도), 추세(EMA200) 위에 있을수록 반등 확률 증가
        # 향후 과제: 실제 과거 백테스트 데이터를 통한 통계 모델(Logistic Regression 등) 연동
        
        # 3.1 승률(Win Probability) 추정치 조정
        base_win_prob = 0.50 # 기본 50:50
        
        # RSI 에 따른 확률 보정 (과매도일수록 반등 확률 up)
        if rsi < 30:
            base_win_prob += 0.15 
        elif rsi < 40:
            base_win_prob += 0.10
        elif rsi > 70:
            base_win_prob -= 0.15 # 과매수 상태의 리픽싱은 신뢰성 하락
            
        # 추세 지표 반영 
        if price_info['ma_cross'].get('price_above_ema200', False):
            base_win_prob += 0.05
            
        base_win_prob = min(max(base_win_prob, 0.1), 0.9) # 10% ~ 90% 제한
        
        # 3.2 이익/손실 산출 로직
        # 발행가 대비 70% 한도 도달 등 추가적인 하방경직성이 있다면 여기서 조정해야 함
        avg_gain = 0.20  # 리픽싱에 따른 평균 기대 반등 수익 (추후 데이터 피팅 필요)
        avg_loss = 0.10  # 리픽싱 효과 실패 시 컷오프(손절) 라인
        
        # 3.3 최종 EV (Expected Value) 산출 
        # EV = (승률 * 평균이익) - (패율 * 평균손실)
        ev = (base_win_prob * avg_gain) - ((1 - base_win_prob) * avg_loss)
        
        # 4. 신호 판별 및 출력
        signal = 'PARTIAL' if ev > 0.03 else 'HOLD'
        if ev > 0.08 and rsi < 40:
            signal = 'ENTER'

        return {
            'ticker': ticker,
            'corp_code': corp_code,
            'latest_notice': report_nm,
            'report_date': latest.get('rcept_dt'),
            'current_price': current_price,
            'rsi': rsi,
            'expected_value': round(ev, 4),
            'win_probability': round(base_win_prob, 2),
            'signal': signal,
            'reason': f"리픽싱({latest.get('rcept_dt')}) 기반 승률 {base_win_prob*100:.0f}%, EV {ev*100:.1f}%",
            'dart_url': f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
        }

if __name__ == "__main__":
    # 테스트 (예: 삼성전자 - 실제론 CB가 없겠지만 로직 테스트용)
    analyzer = CBRefixingAnalyzer()
    res = analyzer.analyze_refixing_opportunity("005930.KS", "00126380")
    print(res)
