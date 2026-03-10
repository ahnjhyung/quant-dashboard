"""
통합 진입 타이밍 분석 엔진
============================
- 다중 지표 신호 가중 합산
- 시장 국면 감지 (Bull/Bear/Sideways)
- 켈리 공식 기반 최적 포지션 사이징
- 자산 클래스별 진입 타이밍 판단
- 매크로 + 기술적 + 온체인 통합 신호
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from analysis.swing_trading import SwingTradingAnalyzer
from analysis.value_investing import ValueInvestingAnalyzer
from analysis.derivatives import DerivativesAnalyzer


class EntryTimingEngine:
    """
    통합 진입 타이밍 엔진
    
    여러 분석 레이어를 결합하여 최종 진입 시점 판단:
    1. 매크로 환경 (VIX, 금리, 달러)
    2. 기술적 지표 (RSI, MACD, 볼린저)
    3. 가치 지표 (PER, PBR, FCF Yield)
    4. 시장 국면 (Bull/Bear/Sideways)
    5. 리스크/리워드 비율
    
    Usage:
        engine = EntryTimingEngine()
        result = engine.analyze_entry("AAPL", asset_class='us_stock')
        btc_timing = engine.analyze_entry("BTC-USD", asset_class='crypto')
    """

    def __init__(self):
        self.swing = SwingTradingAnalyzer()
        self.value = ValueInvestingAnalyzer()
        self.derivatives = DerivativesAnalyzer()

    def detect_market_regime(self) -> dict:
        """
        현재 시장 국면 감지
        
        - Bull: SPY 50MA > 200MA + VIX < 20
        - Bear: SPY 50MA < 200MA + VIX > 25
        - Sideways: 나머지
        
        Returns:
            {
                'regime': 'Bull' | 'Bear' | 'Sideways',
                'vix': 18.5,
                'spy_trend': 'Bullish',
                'confidence': 0.8,
            }
        """
        try:
            # SPY 추세 확인
            spy_data = self.swing.get_ohlcv("SPY", period="1y")
            spy_close = spy_data['Close']
            
            ma50 = spy_close.rolling(50).mean().iloc[-1]
            ma200 = spy_close.rolling(200).mean().iloc[-1]
            spy_trend = 'Bullish' if ma50 > ma200 else 'Bearish'
            spy_rsi = float(self.swing.calculate_rsi(spy_close).iloc[-1])
            
            # VIX 조회
            vix_data = self.derivatives.vix_analysis()
            vix = vix_data.get('vix', 20)
            
            # 달러 인덱스 (DXY)
            dxy_data = self.swing.get_ohlcv("DX-Y.NYB", period="3mo")
            dxy_trend = 'Rising' if not dxy_data.empty and dxy_data['Close'].iloc[-1] > dxy_data['Close'].rolling(20).mean().iloc[-1] else 'Falling'
            
            # 시장 국면 판정
            bull_factors = 0
            bear_factors = 0
            
            if ma50 > ma200:
                bull_factors += 2
            else:
                bear_factors += 2
            
            if vix < 20:
                bull_factors += 1
            elif vix > 30:
                bear_factors += 2
            
            if 40 < spy_rsi < 65:
                bull_factors += 1
            elif spy_rsi > 75:
                bear_factors += 1  # 과매수 = 리스크
            elif spy_rsi < 30:
                bull_factors += 1  # 과매도 = 반등 기회
            
            if dxy_trend == 'Falling':  # 달러 약세 = 위험자산 강세
                bull_factors += 1
            else:
                bear_factors += 1
            
            total = bull_factors + bear_factors
            if total == 0:
                total = 1
            
            bull_ratio = bull_factors / total
            
            if bull_ratio >= 0.65:
                regime = 'Bull 🟢'
                regime_signal = '위험자산 비중 확대 적합'
            elif bull_ratio <= 0.35:
                regime = 'Bear 🔴'
                regime_signal = '방어적 포지션 / 헤지 강화'
            else:
                regime = 'Sideways 🟡'
                regime_signal = '섹터 순환매 / 변동성 매매 유리'
            
            return {
                'regime': regime,
                'regime_signal': regime_signal,
                'bull_ratio': round(bull_ratio, 2),
                'vix': vix,
                'vix_signal': vix_data.get('signal', ''),
                'spy_trend': spy_trend,
                'spy_rsi': round(spy_rsi, 1),
                'spy_ma50': round(float(ma50), 2),
                'spy_ma200': round(float(ma200), 2),
                'dxy_trend': dxy_trend,
                'bull_factors': bull_factors,
                'bear_factors': bear_factors,
            }
        except Exception as e:
            return {'regime': 'Unknown', 'error': str(e)}

    def kelly_position_size(
        self,
        win_probability: float,
        win_return: float,
        loss_return: float,
        capital: float,
        max_risk_pct: float = 0.25  # 켈리 분율 상한 (과도한 집중 방지)
    ) -> dict:
        """
        켈리 공식 포지션 사이징
        
        Full Kelly = (p × b - q) / b
        Half Kelly = Full Kelly / 2 (실용적 권장)
        
        Args:
            win_probability: 이길 확률 (0-1)
            win_return: 이겼을 때 수익률 (소수점, 예: 0.15 = 15%)
            loss_return: 졌을 때 손실률 (소수점, 예: 0.07 = 7%)
            capital: 총 투자 가능 금액 (원 또는 달러)
            max_risk_pct: 최대 투자 비율 한도 (기본 25%)
            
        Returns:
            {
                'full_kelly_pct': 0.35,
                'half_kelly_pct': 0.175,
                'recommended_pct': 0.175,
                'recommended_amount': 1750000,  # capital × recommended_pct
            }
        """
        q = 1 - win_probability  # 실패 확률
        b = win_return / loss_return  # 순수익 / 손실 비율
        
        # 켈리 공식
        full_kelly = (win_probability * b - q) / b
        full_kelly = max(0, full_kelly)  # 음수 방지 (켈리 = 0 → 투자 금지)
        
        half_kelly = full_kelly / 2  # 반켈리 (실용적)
        recommended = min(half_kelly, max_risk_pct)  # 상한 적용
        
        return {
            'win_probability': round(win_probability, 3),
            'loss_probability': round(q, 3),
            'odds_ratio_b': round(b, 2),
            'full_kelly_pct': round(full_kelly * 100, 1),
            'half_kelly_pct': round(half_kelly * 100, 1),
            'recommended_pct': round(recommended * 100, 1),
            'recommended_amount': round(capital * recommended, 0),
            'expected_value': round(win_probability * win_return - q * loss_return, 4),
            'note': '켈리 공식은 장기 기대값 최대화 도구. 실제 투자 시 반켈리(50%) 사용 권장.',
        }

    def analyze_entry(self, ticker: str, asset_class: str = 'us_stock') -> dict:
        """
        특정 자산의 종합 진입 타이밍 분석
        
        Args:
            ticker: 야후파이낸스 티커 ('AAPL', '005930.KS', 'BTC-USD')
            asset_class: 'us_stock', 'kr_stock', 'crypto', 'etf', 'commodity'
            
        Returns:
            종합 진입 신호 딕셔너리
        """
        print(f"🔍 [{ticker}] 진입 타이밍 분석 중...")
        
        results = {
            'ticker': ticker,
            'asset_class': asset_class,
            'analysis_time': datetime.now().isoformat(),
        }
        
        # 1. 기술적 분석
        tech = self.swing.full_analysis(ticker)
        if 'error' in tech:
            results['error'] = tech['error']
            return results
        
        results['technical'] = {
            'rsi': tech['rsi']['value'],
            'macd_signal': tech['macd']['signal'],
            'bb_pct_b': tech['bollinger']['pct_b'],
            'trend': tech['ma_cross']['current_trend'],
            'swing_signal': tech['swing_signal'],
            'swing_confidence': tech['confidence'],
        }
        
        # 2. 기본 가격 정보
        current_price = tech['current_price']
        atr = tech['atr']
        results['price'] = {
            'current': current_price,
            'atr': atr,
            'stop_loss': tech['risk_management']['stop_loss'],
            'target': tech['risk_management']['target'],
            'risk_reward': tech['risk_management']['risk_reward_ratio'],
        }
        
        # 3. 매크로 환경 (미국 주식 / ETF 기준)
        if asset_class in ['us_stock', 'etf', 'crypto']:
            market_regime = self.detect_market_regime()
            results['market_regime'] = market_regime
        
        # 4. 가치 지표 (주식 자산만)
        if asset_class in ['us_stock', 'kr_stock']:
            try:
                piotroski = self.value.piotroski_score(ticker)
                results['fundamentals'] = {
                    'piotroski_score': piotroski['score'],
                    'per': piotroski.get('per', 0),
                    'pbr': piotroski.get('pbr', 0),
                    'roe': piotroski.get('roe', 0),
                    'category': piotroski.get('category', ''),
                }
            except Exception as e:
                results['fundamentals'] = {'error': str(e)}
        
        # 5. 포지션 사이징 (기술적 신호 기반)
        rsi = tech['rsi']['value']
        bb_pct = tech['bollinger']['pct_b']
        confidence = tech['confidence']
        
        # RSI + 볼린저 기반 승률 추정
        if rsi < 30 and bb_pct < 0.1:
            win_prob = 0.65  # 과매도 구간 역발상
        elif rsi > 70 and bb_pct > 0.9:
            win_prob = 0.35  # 과매수는 불리
        else:
            win_prob = 0.5 + (confidence - 0.5) * 0.3
        
        risk_pct = (current_price - tech['risk_management']['stop_loss']) / current_price
        reward_pct = (tech['risk_management']['target'] - current_price) / current_price
        
        sizing = self.kelly_position_size(
            win_probability=win_prob,
            win_return=reward_pct,
            loss_return=abs(risk_pct),
            capital=10_000_000  # 1천만원 기준 예시
        )
        results['position_sizing'] = sizing
        
        # 6. 최종 진입 판정
        bull_score = 0
        
        if 'BUY' in tech['swing_signal']:
            bull_score += 3
        elif 'SELL' in tech['swing_signal']:
            bull_score -= 3
        
        if asset_class in ['us_stock', 'etf'] and 'market_regime' in results:
            regime = results['market_regime'].get('regime', '')
            if 'Bull' in regime:
                bull_score += 2
            elif 'Bear' in regime:
                bull_score -= 2
        
        if asset_class in ['us_stock', 'kr_stock'] and 'fundamentals' in results:
            f_score = results['fundamentals'].get('piotroski_score', 5)
            if f_score >= 7:
                bull_score += 1
            elif f_score <= 3:
                bull_score -= 1
        
        if bull_score >= 4:
            entry_signal = '✅ 진입 적합 (강한 매수 신호)'
            entry_type = 'ENTER'
        elif bull_score >= 2:
            entry_signal = '🔶 분할 진입 고려 (조심스러운 매수)'
            entry_type = 'PARTIAL'
        elif bull_score <= -4:
            entry_signal = '❌ 진입 부적합 (강한 매도/회피 신호)'
            entry_type = 'AVOID'
        elif bull_score <= -2:
            entry_signal = '⚠️ 진입 대기 (하락 추세 진행 중)'
            entry_type = 'WAIT'
        else:
            entry_signal = '⏸️ 관망 (중립 신호)'
            entry_type = 'HOLD'
        
        results['final'] = {
            'entry_signal': entry_signal,
            'entry_type': entry_type,
            'bull_score': bull_score,
            'recommended_action': entry_signal,
        }
        
        return results

    def scan_multiple(self, tickers: list, asset_class: str = 'us_stock') -> list:
        """
        여러 종목 일괄 스캔 (대시보드 테이블용)
        """
        results = []
        for ticker in tickers:
            try:
                result = self.analyze_entry(ticker, asset_class)
                results.append({
                    'ticker': ticker,
                    'price': result.get('price', {}).get('current', 0),
                    'rsi': result.get('technical', {}).get('rsi', 0),
                    'signal': result.get('technical', {}).get('swing_signal', 'N/A'),
                    'confidence': result.get('technical', {}).get('swing_confidence', 0),
                    'entry': result.get('final', {}).get('entry_type', 'N/A'),
                    'stop': result.get('price', {}).get('stop_loss', 0),
                    'target': result.get('price', {}).get('target', 0),
                    'rr': result.get('price', {}).get('risk_reward', 0),
                })
            except Exception as e:
                results.append({'ticker': ticker, 'error': str(e)})
        return results


if __name__ == "__main__":
    engine = EntryTimingEngine()
    
    print("[1] 시장 국면 감지...")
    regime = engine.detect_market_regime()
    print(f"    국면: {regime['regime']}")
    print(f"    VIX: {regime['vix']}")
    print(f"    SPY 추세: {regime['spy_trend']}")
    
    print("\n[2] 켈리 공식 포지션 사이징...")
    sizing = engine.kelly_position_size(
        win_probability=0.60,
        win_return=0.15,
        loss_return=0.07,
        capital=10_000_000
    )
    print(f"    Full Kelly: {sizing['full_kelly_pct']}%")
    print(f"    반켈리 권장: {sizing['half_kelly_pct']}%")
    print(f"    1천만원 기준 투자액: ₩{sizing['recommended_amount']:,.0f}")
    
    print("\n[3] AAPL 진입 타이밍...")
    result = engine.analyze_entry("AAPL", "us_stock")
    print(f"    가격: ${result['price']['current']}")
    print(f"    기술적 신호: {result['technical']['swing_signal']}")
    print(f"    최종 판정: {result['final']['entry_signal']}")
