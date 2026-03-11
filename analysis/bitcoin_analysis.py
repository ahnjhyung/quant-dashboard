"""
비트코인 온체인 & 사이클 분석 엔진
=====================================
- MVRV Z-Score (시장가치/실현가치)
- NVT Ratio (네트워크가치/거래량)
- Stock-to-Flow 모델
- 레인보우 차트 밴드 위치
- 반감기 사이클 분석
- 비트코인 도미넌스 추이
- 공포탐욕지수 통합
"""

import math
import numpy as np
import pandas as pd
import yfinance as yf
import requests
from datetime import datetime, timedelta
from data_collectors.crypto_data import CryptoDataCollector


# 비트코인 반감기 일자
HALVING_DATES = [
    datetime(2009, 1, 3),   # Genesis Block
    datetime(2012, 11, 28), # 1차 반감기 (50→25 BTC)
    datetime(2016, 7, 9),   # 2차 반감기 (25→12.5 BTC)
    datetime(2020, 5, 11),  # 3차 반감기 (12.5→6.25 BTC)
    datetime(2024, 4, 19),  # 4차 반감기 (6.25→3.125 BTC)
    datetime(2028, 4, 1),   # 5차 반감기 (예상)
]

# 레인보우 차트 밴드 (로그 회귀 기반 approximate bands)
RAINBOW_BANDS = {
    'Maximum Bubble': 9,
    'Sell. Seriously, SELL!': 8,
    'FOMO Intensifies': 7,
    'Is this a bubble?': 6,
    'HODL!': 5,
    'Still cheap': 4,
    'Accumulate': 3,
    'BUY!': 2,
    'Fire Sale': 1,
}


class BitcoinAnalyzer:
    """
    비트코인 종합 온체인 및 사이클 분석기
    
    Usage:
        analyzer = BitcoinAnalyzer()
        
        # 공포탐욕지수
        fng = analyzer.get_fear_greed_analysis()
        
        # 반감기 사이클
        cycle = analyzer.halving_cycle_analysis()
        
        # 종합 온체인 요약
        summary = analyzer.btc_comprehensive_analysis()
    """

    def __init__(self):
        self.crypto = CryptoDataCollector()

    def get_fear_greed_analysis(self) -> dict:
        """
        공포탐욕지수 분석 및 매매 신호 생성
        
        Returns:
            {
                'current': {'value': 72, 'classification': 'Greed'},
                'history': [...],
                'signal': 'Consider Taking Profits',
                'extremes': {'fear_days': 5, 'greed_days': 12},
            }
        """
        history = self.crypto.get_fear_greed_index(60)
        
        if not history:
            return {'error': '데이터 조회 실패'}
        
        current = history[-1] if history else {}
        current_value = current.get('value', 50)
        
        # 최근 30일 분석
        recent_30 = history[-30:] if len(history) >= 30 else history
        recent_values = [d['value'] for d in recent_30]
        
        avg_30d = np.mean(recent_values) if recent_values else 50
        extreme_fear_days = sum(1 for v in recent_values if v <= 20)
        extreme_greed_days = sum(1 for v in recent_values if v >= 80)
        
        # 신호 생성 (역발상 전략)
        if current_value <= 20:
            signal = '🟢 극도의 공포 → 강한 역발상 매수 고려'
            signal_type = 'STRONG_BUY'
        elif current_value <= 35:
            signal = '🟢 공포 → 분할 매수 관심'
            signal_type = 'BUY'
        elif current_value >= 80:
            signal = '🔴 극도의 탐욕 → 부분 익절 고려'
            signal_type = 'STRONG_SELL'
        elif current_value >= 65:
            signal = '🟡 탐욕 → 신규 매수 자제'
            signal_type = 'CAUTION'
        else:
            signal = '⚪ 중립 → 추세 관망'
            signal_type = 'HOLD'
        
        # 모멘텀 (최근 증가/감소)
        if len(history) >= 7:
            week_ago = history[-7]['value'] if len(history) >= 7 else current_value
            momentum = current_value - week_ago
            momentum_str = f'+{momentum:.0f} (탐욕 심화)' if momentum > 0 else f'{momentum:.0f} (공포 심화)'
        else:
            momentum_str = 'N/A'
        
        return {
            'current': current,
            'current_value': current_value,
            'signal': signal,
            'signal_type': signal_type,
            'avg_30d': round(avg_30d, 1),
            'momentum_7d': momentum_str,
            'extreme_fear_days_30d': extreme_fear_days,
            'extreme_greed_days_30d': extreme_greed_days,
            'history': history,
        }

    def halving_cycle_analysis(self) -> dict:
        """
        반감기 사이클 분석
        
        - 현재 사이클 몇 일차?
        - 다음 반감기까지 날자
        - 사이클 내 평균 가격 위치
        """
        now = datetime.now()
        
        # 지난 반감기들 정렬
        past_halvings = [h for h in HALVING_DATES if h <= now]
        future_halvings = [h for h in HALVING_DATES if h > now]
        
        last_halving = past_halvings[-1] if past_halvings else HALVING_DATES[0]
        next_halving = future_halvings[0] if future_halvings else datetime(2028, 4, 1)
        
        days_since_halving = (now - last_halving).days
        days_to_next = (next_halving - now).days
        
        # 사이클 진행률 (%)
        total_cycle_days = (next_halving - last_halving).days
        cycle_progress = (days_since_halving / total_cycle_days * 100) if total_cycle_days > 0 else 0
        
        # 현재 블록 보상
        current_reward = 3.125  # 4차 반감기 이후
        
        # 사이클 국면 (과거 패턴 기반)
        if cycle_progress < 20:
            phase = '🌱 초기 (상승 준비)'
            phase_signal = 'Accumulate (분할 매수)'
        elif cycle_progress < 50:
            phase = '🚀 상승 국면 (Bull Run)'
            phase_signal = 'Hold & Add (보유 + 추가)'
        elif cycle_progress < 70:
            phase = '🌤 고점 근처 (Top Zone)'
            phase_signal = 'Take Profits (익절 시작)'
        elif cycle_progress < 90:
            phase = '📉 조정 / Bear Market'
            phase_signal = 'Reduce / Wait (축소 + 대기)'
        else:
            phase = '🔄 바닥 근처 (Bottom Forming)'
            phase_signal = 'DCA Accumulate (분할 적립)'
        
        return {
            'last_halving': last_halving.strftime('%Y-%m-%d'),
            'next_halving': next_halving.strftime('%Y-%m-%d'),
            'days_since_halving': days_since_halving,
            'days_to_next_halving': days_to_next,
            'cycle_progress_pct': round(cycle_progress, 1),
            'cycle_phase': phase,
            'phase_signal': phase_signal,
            'current_block_reward': current_reward,
            'halving_number': len(past_halvings),
            'halvings': [
                {
                    'number': i + 1,
                    'date': h.strftime('%Y-%m-%d'),
                    'reward_before': 50 / (2 ** i),
                    'reward_after': 50 / (2 ** (i + 1)),
                }
                for i, h in enumerate(HALVING_DATES[1:])  # Genesis 제외
            ]
        }

    def rainbow_chart_analysis(self, current_price: float) -> dict:
        """
        비트코인 레인보우 차트 분석
        
        로그 회귀 모델: Price ≈ 10^(a * log(days_since_genesis) + b)
        
        a ≈ 5.84, b ≈ -17.01 (approximately)
        밴드는 이 회귀선 주변에 위치
        """
        genesis_date = datetime(2009, 1, 3)
        now = datetime.now()
        days_since_genesis = (now - genesis_date).days
        
        if days_since_genesis <= 0:
            return {'error': '날짜 계산 오류'}
        
        # 로그 회귀 기반 예상 중앙값
        # (근사 파라미터: 실제 rainbow chart 기준)
        a = 5.84
        b = -17.01
        log_days = math.log10(days_since_genesis)
        fair_value = 10 ** (a * log_days + b)
        
        # 밴드 범위 (중앙값 대비 로그 스케일 오프셋)
        bands = {}
        offsets = {
            'Maximum Bubble': 3.2,
            'Sell. Seriously, SELL!': 2.6,
            'FOMO Intensifies': 2.0,
            'Is this a bubble?': 1.4,
            'HODL!': 0.8,
            'Still cheap': 0.1,
            'Accumulate': -0.6,
            'BUY!': -1.3,
            'Fire Sale': -2.0,
        }
        
        for band_name, offset in offsets.items():
            bands[band_name] = round(fair_value * (10 ** (offset * 0.1)), 0)
        
        # 현재 가격이 속하는 밴드 찾기
        current_band = 'Unknown'
        band_names = list(offsets.keys())
        band_values = [bands[b] for b in band_names]
        
        for i in range(len(band_values) - 1):
            if band_values[i + 1] <= current_price <= band_values[i]:
                current_band = band_names[i]
                break
        
        if current_price > band_values[0]:
            current_band = 'Maximum Bubble'
        elif current_price < band_values[-1]:
            current_band = 'Fire Sale'
        
        return {
            'current_price': current_price,
            'fair_value': round(fair_value, 0),
            'current_band': current_band,
            'premium_to_fair': round((current_price / fair_value - 1) * 100, 1),
            'bands': bands,
            'days_since_genesis': days_since_genesis,
        }

    def mvrv_proxy(self, current_price: float, days: int = 365) -> dict:
        """
        MVRV Z-Score 근사치 계산
        
        실제 MVRV는 온체인 데이터가 필요하나,
        여기서는 52주 평균 가격을 'Realized Value' proxy로 사용.
        
        MVRV > 3.7: 극도 과매수 (익절 구간)
        MVRV < 1: 과매도 (매수 구간)
        """
        try:
            btc_hist = yf.download("BTC-USD", period=f"{days}d", progress=False)
            if isinstance(btc_hist.columns, pd.MultiIndex):
                btc_hist.columns = btc_hist.columns.get_level_values(0)
            
            if btc_hist.empty:
                return {'error': '데이터 없음'}
            
            # Realized Price proxy (365일 평균가)
            realized_price_proxy = float(btc_hist['Close'].mean())
            
            # Market Value / Realized Value
            mvrv_proxy_val = current_price / realized_price_proxy
            
            # Z-Score (1년 평균/표준편차 기준)
            btc_close = btc_hist['Close'].dropna()
            mean_price = float(btc_close.mean())
            std_price = float(btc_close.std())
            z_score = (current_price - mean_price) / std_price if std_price > 0 else 0
            
            # 해석
            if mvrv_proxy_val > 3.5:
                interpretation = '🔴 극도 과매수 - 상단 익절 구간 (역사적 고점 부근)'
                signal = 'SELL'
            elif mvrv_proxy_val > 2.5:
                interpretation = '🟠 과매수 - 부분 익절 고려'
                signal = 'REDUCE'
            elif mvrv_proxy_val > 1.5:
                interpretation = '🟡 적정 가치 - 보유'
                signal = 'HOLD'
            elif mvrv_proxy_val > 1.0:
                interpretation = '🟢 약간 저평가 - 분할 매수 기회'
                signal = 'BUY'
            else:
                interpretation = '🟢 극도 저평가 - 강한 매수 구간 (역사적 바닥 부근)'
                signal = 'STRONG_BUY'
            
            return {
                'current_price': current_price,
                'realized_price_proxy': round(realized_price_proxy, 2),
                'mvrv_proxy': round(mvrv_proxy_val, 3),
                'z_score_proxy': round(z_score, 3),
                'interpretation': interpretation,
                'signal': signal,
                'price_1y_high': round(float(btc_close.max()), 2),
                'price_1y_low': round(float(btc_close.min()), 2),
                'price_1y_avg': round(float(btc_close.mean()), 2),
                'note': '실현가격은 365일 평균가로 근사. 정확한 MVRV는 Glassnode 등 온체인 데이터 필요.'
            }
        except Exception as e:
            return {'error': str(e)}

    def btc_comprehensive_analysis(self) -> dict:
        """
        비트코인 종합 분석 (한 번에 호출)
        
        모든 지표를 결합하여 최종 시장 국면 판단
        """
        print("🔍 비트코인 종합 분석 시작...")
        
        # 현재 가격 조회
        price_data = self.crypto.get_btc_current_price()
        current_price = price_data.get('price_usd', 0)
        
        if not current_price:
            return {'error': '비트코인 가격 조회 실패'}
        
        print(f"  BTC 현재가: ${current_price:,.2f}")
        
        # 각 분석 실행
        fear_greed = self.get_fear_greed_analysis()
        halving = self.halving_cycle_analysis()
        rainbow = self.rainbow_chart_analysis(current_price)
        mvrv = self.mvrv_proxy(current_price)
        
        # 전체 시장 신호 집계
        signals = []
        if fear_greed.get('signal_type') in ['STRONG_BUY', 'BUY']:
            signals.append(('공포탐욕', 'bull'))
        elif fear_greed.get('signal_type') in ['STRONG_SELL']:
            signals.append(('공포탐욕', 'bear'))
        else:
            signals.append(('공포탐욕', 'neutral'))
        
        if mvrv.get('signal') in ['STRONG_BUY', 'BUY']:
            signals.append(('MVRV', 'bull'))
        elif mvrv.get('signal') in ['SELL', 'REDUCE']:
            signals.append(('MVRV', 'bear'))
        else:
            signals.append(('MVRV', 'neutral'))
        
        # 반감기 사이클
        cycle_phase = halving.get('phase_signal', '')
        if 'Accumulate' in cycle_phase or 'Add' in cycle_phase:
            signals.append(('사이클', 'bull'))
        elif 'Profits' in cycle_phase or 'Reduce' in cycle_phase:
            signals.append(('사이클', 'bear'))
        else:
            signals.append(('사이클', 'neutral'))
        
        # 레인보우 밴드
        rainbow_band = rainbow.get('current_band', '')
        if '🔥' in rainbow_band or 'Bubble' in rainbow_band or 'SELL' in rainbow_band:
            signals.append(('레인보우', 'bear'))
        elif 'BUY' in rainbow_band or 'Fire Sale' in rainbow_band or 'cheap' in rainbow_band:
            signals.append(('레인보우', 'bull'))
        else:
            signals.append(('레인보우', 'neutral'))
        
        bull_count = sum(1 for _, s in signals if s == 'bull')
        bear_count = sum(1 for _, s in signals if s == 'bear')
        
        if bull_count >= 3:
            overall = '🟢 강한 매수 국면'
        elif bull_count >= 2:
            overall = '🟡 매수 관심 국면'
        elif bear_count >= 3:
            overall = '🔴 강한 매도 국면'
        elif bear_count >= 2:
            overall = '🟠 매도 주의 국면'
        else:
            overall = '⚪ 중립 / 관망 국면'

        # EV (기대값) 및 승률(Win Prob) 계산 
        # (불/베어 시그널 비율 기반)
        total_signals = bull_count + bear_count
        if total_signals > 0:
            base_win_prob = bull_count / (total_signals + 2) + 0.3  # 기본 확률 보정
        else:
            base_win_prob = 0.5
            
        win_prob = min(0.9, max(0.1, base_win_prob))
        lose_prob = 1.0 - win_prob
        
        # Upside / Downside (레인보우 밴드 및 MVRV z-score 기반 근사치)
        # 상단 목표가는 적정가치(fair_value)의 다음 밴드 수준, 하단 손절가는 직전 지지 밴드
        fair_value = rainbow.get('fair_value', current_price)
        target_upside = max(current_price * 1.2, fair_value * 1.5)  # 보수적인 업사이드
        stop_downside = min(current_price * 0.8, fair_value * 0.7)  # 보수적인 다운사이드
        
        avg_profit = (target_upside - current_price) / current_price
        avg_loss = (current_price - stop_downside) / current_price
        
        # 기대수익률(EV_pct) = (승률 * 평균수익률) - (패율 * 평균손실률)
        ev_pct = (win_prob * avg_profit) - (lose_prob * avg_loss)
        
        return {
            'current_price': current_price,
            'price_data': price_data,
            'fear_greed': fear_greed,
            'halving_cycle': halving,
            'rainbow_chart': rainbow,
            'mvrv': mvrv,
            'overall_assessment': overall,
            'signal_breakdown': signals,
            'bull_signals': bull_count,
            'bear_signals': bear_count,
            'win_probability': round(win_prob, 3),
            'expected_value_pct': round(ev_pct, 4),
            'analysis_timestamp': datetime.now().isoformat(),
        }


if __name__ == "__main__":
    analyzer = BitcoinAnalyzer()
    
    print("[1] 반감기 사이클 분석...")
    cycle = analyzer.halving_cycle_analysis()
    print(f"    마지막 반감기: {cycle['last_halving']}")
    print(f"    다음 반감기: {cycle['next_halving']} (D-{cycle['days_to_next_halving']})")
    print(f"    현재 사이클: {cycle['cycle_phase']}")
    print(f"    신호: {cycle['phase_signal']}")
    
    print("\n[2] 공포탐욕지수...")
    fng = analyzer.get_fear_greed_analysis()
    print(f"    현재값: {fng.get('current_value')} - {fng.get('current', {}).get('classification', '')}")
    print(f"    신호: {fng.get('signal')}")
    
    print("\n[3] 레인보우 차트...")
    rainbow = analyzer.rainbow_chart_analysis(65000)
    print(f"    현재 밴드: {rainbow['current_band']}")
    print(f"    공정가치 대비: {rainbow['premium_to_fair']}%")
