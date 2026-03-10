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
        
        # 3. 기대값(EV) 추정 (가설: 바닥권(RSI < 40)에서 리픽싱 완료 시 반등 확률 높음)
        # 승률 계산: RSI가 낮을수록, 200 EMA 위에 있을수록 높게 산정
        base_win_prob = 0.55
        if rsi < 40: base_win_prob += 0.1
        if price_info['ma_cross'].get('price_above_ema200'): base_win_prob += 0.1
        
        avg_gain = 0.20  # 리픽싱 후 반등 시 평균 20% 이익 가정
        avg_loss = 0.10  # 추가 하락 시 10% 손실 가정
        
        ev = (base_win_prob * avg_gain) - ((1 - base_win_prob) * avg_loss)
        
        signal = 'PARTIAL' if ev > 0.05 else 'HOLD'
        if ev > 0.10 and rsi < 35:
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
            'reason': f"리픽싱 공시 발견 ({latest.get('rcept_dt')}) 및 EV {ev*100:.1f}% 산출",
            'dart_url': f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
        }

if __name__ == "__main__":
    # 테스트 (예: 삼성전자 - 실제론 CB가 없겠지만 로직 테스트용)
    analyzer = CBRefixingAnalyzer()
    res = analyzer.analyze_refixing_opportunity("005930.KS", "00126380")
    print(res)
