"""
전환사채(CB) 리픽싱(전환가액 조정) 분석 엔진
============================================
- DART 공시로부터 전환가액 조정 내역 분석
- 리픽싱 후 주가 하락 방어력 및 반등 기대값(EV) 산출
- 전환사채 희석 물량 및 전환 가능 시기 계산
"""

import pandas as pd
import numpy as np
import re
from datetime import datetime, timedelta
from data_collectors.open_dart import OpenDartCollector
from analysis.swing_trading import SwingTradingAnalyzer

class CBRefixingAnalyzer:
    """
    CB 리픽싱 분석기 (고도화 버전)
    
    리픽싱(Refixing)은 주가가 떨어졌을 때 전환가도 같이 낮춰주는 조항입니다.
    바닥권에서 리픽싱이 완료된 종목은 '안전마진'이 확보된 것으로 간주합니다.
    """

    def __init__(self):
        self.dart = OpenDartCollector()
        self.swing = SwingTradingAnalyzer()

    def analyze_refixing_opportunity(self, ticker: str, corp_code: str) -> dict:
        """
        특정 종목의 최신 리픽싱 공시 분석 및 기대값 산출 (고도화 버전)
        """
        print(f"🕵️ [{ticker}] CB 리픽싱 정밀 분석 중...")
        
        # 1. 최신 리픽싱 공시 조회
        notices = self.dart.get_cb_refixing_notices(corp_code, bgn_de=(datetime.now() - timedelta(days=90)).strftime('%Y%m%d'))
        
        if not notices:
            return {'ticker': ticker, 'signal': 'NONE', 'reason': '최근 90일 내 리픽싱 공시 없음'}

        # 최신 공시 기준
        latest = notices[0]
        report_nm = latest.get('report_nm', '')
        rcept_no = latest.get('rcept_no', '')
        
        # 2. 공시 본문 파싱 (최저 한도 추출)
        doc_xml = self.dart.get_disclosure_document(rcept_no)
        refix_limit_ratio = 70.0 # 기본값
        original_price = 0
        adjusted_price = 0

        if doc_xml:
            # 텍스트에서 '최저조정가액' 또는 관련 문구 검색
            limit_match = re.search(r'최초\s*전환가액의\s*(\d+)%', doc_xml)
            if limit_match:
                refix_limit_ratio = float(limit_match.group(1))
            
            # 가격 추출 시도
            prices = re.findall(r'(\d{1,3}(?:,\d{3})+)\s*원', doc_xml)
            if len(prices) >= 2:
                p1 = int(prices[0].replace(',', ''))
                p2 = int(prices[1].replace(',', ''))
                original_price = max(p1, p2)
                adjusted_price = min(p1, p2)

        # 3. 현재 주가 및 추세 확인
        price_info = self.swing.full_analysis(ticker)
        if 'error' in price_info:
            return {'ticker': ticker, 'error': '주가 데이터 로드 실패'}
            
        current_price = price_info['current_price']
        rsi = price_info['rsi']['value']
        
        # 4. 기대값(EV) 정밀 추정
        # 4.1 하방 경직성(Safety Margin) 계산
        floor_price = original_price * (refix_limit_ratio / 100) if original_price > 0 else adjusted_price * 0.95
        distance_to_floor = (current_price / floor_price - 1) * 100 if floor_price > 0 else 10.0
        
        safety_score = 0
        if distance_to_floor <= 5: 
            safety_score = 0.20
        elif distance_to_floor <= 10:
            safety_score = 0.10

        # 4.2 승률(Win Probability) 보정
        base_win_prob = 0.50
        if rsi < 30: base_win_prob += 0.15 
        elif rsi < 40: base_win_prob += 0.05
        
        if price_info.get('ma_cross', {}).get('price_above_ema200', False):
            base_win_prob += 0.05
            
        base_win_prob += safety_score
        base_win_prob = min(max(base_win_prob, 0.1), 0.9)
        
        # 4.3 평균 손익비 설정
        avg_gain = 0.15 + (safety_score * 0.5) 
        avg_loss = 0.08 - (safety_score * 0.2) 
        
        ev = (base_win_prob * avg_gain) - ((1 - base_win_prob) * avg_loss)
        
        # 5. 최종 신호
        signal = 'HOLD'
        if ev > 0.08: signal = 'ENTER'
        elif ev > 0.04: signal = 'PARTIAL'

        return {
            'ticker': ticker,
            'corp_code': corp_code,
            'report_name': report_nm,
            'current_price': current_price,
            'adjusted_price': adjusted_price,
            'floor_price': round(floor_price, 0),
            'distance_to_floor_pct': round(distance_to_floor, 2),
            'rsi': rsi,
            'expected_value': round(ev, 4),
            'win_probability': round(base_win_prob, 2),
            'signal': signal,
            'reason': f"리픽싱 바닥 접근 ({distance_to_floor:.1f}% 남음), EV {ev*100:.1f}%",
            'dart_url': f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
        }

if __name__ == "__main__":
    # 테스트 (예: 삼성전자)
    analyzer = CBRefixingAnalyzer()
    res = analyzer.analyze_refixing_opportunity("005930.KS", "00126380")
    print(res)
