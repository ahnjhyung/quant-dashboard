"""
파생상품 분석 엔진
==================
- Black-Scholes 옵션 이론가 계산
- 옵션 Greeks (Delta, Gamma, Theta, Vega, Rho)
- Put-Call Ratio (PCR) 분석
- VIX 기간구조 (Term Structure)
- 선물 베이시스 계산
- 현물 + 옵션 혼합 포지션 P&L 시뮬레이션
"""

import math
import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm
from typing import Optional


class DerivativesAnalyzer:
    """
    파생상품 분석 도구
    
    Usage:
        analyzer = DerivativesAnalyzer()
        
        # 옵션 가격 및 Greeks
        price, greeks = analyzer.black_scholes(S=150, K=155, T=30, r=0.05, sigma=0.25, option_type='call')
        
        # 포지션 P&L 시뮬레이션
        pnl = analyzer.simulate_portfolio_pnl(
            spot_qty=100,         # 현물 100주 보유
            options=[
                {'type': 'put', 'K': 145, 'qty': 1, 'premium': 3.5}  # 방어 풋 1계약 매수
            ],
            price_range=(100, 200)
        )
    """

    def __init__(self):
        pass

    def black_scholes(
        self,
        S: float,      # 현재 주가
        K: float,      # 행사가
        T: float,      # 만기일까지 일수 (예: 30일 = 30)
        r: float,      # 무위험이자율 (소수점, 예: 0.05)
        sigma: float,  # 내재변동성 (소수점, 예: 0.25 = 25%)
        option_type: str = 'call',  # 'call' 또는 'put'
        q: float = 0.0  # 연간 배당수익률
    ) -> dict:
        """
        Black-Scholes 옵션 이론가 및 Greeks 계산
        
        Args:
            S: 현재 기초자산 가격
            K: 행사가 (Strike Price)
            T: 잔존 만기 (일 단위, 내부에서 연환산)
            r: 무위험이자율 (annual, decimal)
            sigma: 변동성 (annual, decimal)
            option_type: 'call' 또는 'put'
            q: 배당 수익률 (annual, decimal)
            
        Returns:
            {
                'price': 5.23,       # 이론 가격
                'delta': 0.52,       # Delta
                'gamma': 0.02,       # Gamma
                'theta': -0.04,      # Theta (일당)
                'vega': 0.30,        # Vega (변동성 1% 변화 시)
                'rho': 0.08,         # Rho (금리 1% 변화 시)
                'iv': 0.25,
                'intrinsic_value': 0.0,
                'time_value': 5.23,
                'moneyness': 'OTM',
            }
        """
        # 연환산 만기
        T_years = T / 365.0
        
        if T_years <= 0 or sigma <= 0:
            return {'error': '만기 또는 변동성이 0 이하입니다.'}
        
        # d1, d2 계산
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T_years) / (sigma * math.sqrt(T_years))
        d2 = d1 - sigma * math.sqrt(T_years)
        
        # 옵션 가격
        if option_type.lower() == 'call':
            price = (S * math.exp(-q * T_years) * norm.cdf(d1) -
                     K * math.exp(-r * T_years) * norm.cdf(d2))
            delta = math.exp(-q * T_years) * norm.cdf(d1)
            rho = K * T_years * math.exp(-r * T_years) * norm.cdf(d2) / 100
        else:  # put
            price = (K * math.exp(-r * T_years) * norm.cdf(-d2) -
                     S * math.exp(-q * T_years) * norm.cdf(-d1))
            delta = -math.exp(-q * T_years) * norm.cdf(-d1)
            rho = -K * T_years * math.exp(-r * T_years) * norm.cdf(-d2) / 100
        
        # 공통 Greeks
        gamma = (math.exp(-q * T_years) * norm.pdf(d1)) / (S * sigma * math.sqrt(T_years))
        vega = S * math.exp(-q * T_years) * norm.pdf(d1) * math.sqrt(T_years) / 100  # 1% 변동
        
        # Theta (1일 기준)
        theta_call = (-(S * math.exp(-q * T_years) * norm.pdf(d1) * sigma / (2 * math.sqrt(T_years)))
                      - r * K * math.exp(-r * T_years) * norm.cdf(d2)
                      + q * S * math.exp(-q * T_years) * norm.cdf(d1)) / 365
        theta_put = (-(S * math.exp(-q * T_years) * norm.pdf(d1) * sigma / (2 * math.sqrt(T_years)))
                     + r * K * math.exp(-r * T_years) * norm.cdf(-d2)
                     - q * S * math.exp(-q * T_years) * norm.cdf(-d1)) / 365
        theta = theta_call if option_type.lower() == 'call' else theta_put
        
        # 내재가치 및 시간가치
        if option_type.lower() == 'call':
            intrinsic = max(S - K, 0)
        else:
            intrinsic = max(K - S, 0)
        time_value = max(price - intrinsic, 0)
        
        # 머니니스 (ITM/ATM/OTM)
        if option_type.lower() == 'call':
            if S > K * 1.02:
                moneyness = 'ITM (내가격)'
            elif S < K * 0.98:
                moneyness = 'OTM (외가격)'
            else:
                moneyness = 'ATM (등가격)'
        else:
            if S < K * 0.98:
                moneyness = 'ITM (내가격)'
            elif S > K * 1.02:
                moneyness = 'OTM (외가격)'
            else:
                moneyness = 'ATM (등가격)'
        
        return {
            'option_type': option_type.upper(),
            'price': round(price, 4),
            'delta': round(delta, 4),
            'gamma': round(gamma, 6),
            'theta': round(theta, 4),
            'vega': round(vega, 4),
            'rho': round(rho, 4),
            'iv': sigma,
            'intrinsic_value': round(intrinsic, 4),
            'time_value': round(time_value, 4),
            'moneyness': moneyness,
            'd1': round(d1, 4),
            'd2': round(d2, 4),
            'params': {'S': S, 'K': K, 'T_days': T, 'r': r, 'sigma': sigma}
        }

    def option_pnl_at_expiry(
        self,
        option_type: str,
        K: float,
        premium: float,
        qty: int,
        price_range: tuple
    ) -> pd.DataFrame:
        """
        옵션 만기 손익 계산
        
        Args:
            option_type: 'call_long', 'call_short', 'put_long', 'put_short'
            K: 행사가
            premium: 프리미엄 (지급한 금액)
            qty: 계약 수 (1계약 = 100주 기준)
            price_range: (최소가, 최대가) 시뮬레이션 범위
            
        Returns:
            DataFrame with ['price', 'pnl']
        """
        prices = np.linspace(price_range[0], price_range[1], 200)
        multiplier = 100 * qty  # 1계약 = 100주
        
        if option_type == 'call_long':
            pnl = np.where(prices > K, (prices - K - premium) * multiplier, -premium * multiplier)
        elif option_type == 'put_long':
            pnl = np.where(prices < K, (K - prices - premium) * multiplier, -premium * multiplier)
        elif 'short' in option_type.lower() or '매도' in option_type:
            # [SECURITY] 숏포지션 금지 (사용자 요청: 매도 포지션은 너무 위험하고 예탁금 부족)
            pnl = np.full(len(prices), -premium * multiplier * 100) # 패널티 부여
            print(f"🚨 [CRITICAL] {option_type} is FORBIDDEN. Only Long positions are allowed.")
        else:
            pnl = np.zeros(len(prices))
        
        return pd.DataFrame({'price': prices, 'pnl': pnl})

    def simulate_portfolio_pnl(
        self,
        spot_qty: int = 0,
        spot_avg_price: float = 0,
        options: list = None,
        price_range: tuple = None,
        num_points: int = 200,
        current_price: float = None,
        volatility: float = 0.20,
        days_to_expiry: float = 30.0
    ) -> dict:
        """
        현물 + 옵션 혼합 포지션 P&L 시뮬레이션
        추가로 Black-Scholes 기반의 Log-normal 확률분포를 적용하여 기댓값(EV 달러)과 승률 계산
        
        Args:
            spot_qty: 현물 보유 수량 (음수=숏)
            spot_avg_price: 현물 평균 매수가
            options: [
                {
                    'type': 'call_long' | 'call_short' | 'put_long' | 'put_short',
                    'K': 행사가,
                    'premium': 프리미엄,
                    'qty': 계약수
                }, ...
            ]
            price_range: (최솟값, 최댓값)
            current_price: 현재 주가 (미입력 시 spot_avg_price 사용)
            volatility: 내재변동성 (기본 0.20 = 20%)
            days_to_expiry: 옵션 만기까지 남은 일수
            
        Returns:
            {
                'prices': [...],
                'spot_pnl': [...],
                'option_pnl': [...],
                'total_pnl': [...],
                'breakeven': [...],
                'max_profit': ...,
                'max_loss': ...,
                'win_probability': 0.65,
                'expected_value': 125.40,
                'expected_value_note': '...',
            }
        """
        if options is None:
            options = []
        if price_range is None:
            base = spot_avg_price if spot_avg_price else 100
            price_range = (base * 0.7, base * 1.3)
        
        prices = np.linspace(price_range[0], price_range[1], num_points)
        
        # 현물 P&L
        spot_pnl = (prices - spot_avg_price) * spot_qty if spot_avg_price and spot_qty else np.zeros(num_points)
        
        # 옵션 통합 P&L
        total_option_pnl = np.zeros(num_points)
        option_details = []
        
        for opt in options:
            opt_df = self.option_pnl_at_expiry(
                opt['type'], opt['K'], opt['premium'], opt['qty'], price_range
            )
            pnl_arr = np.interp(prices, opt_df['price'], opt_df['pnl'])
            total_option_pnl += pnl_arr
            option_details.append({
                'type': opt['type'],
                'K': opt['K'],
                'premium': opt['premium'],
                'qty': opt['qty'],
            })
        
        total_pnl = spot_pnl + total_option_pnl
        
        # 손익분기점 (부호 변환 지점)
        sign_changes = np.where(np.diff(np.sign(total_pnl)))[0]
        breakevens = [round(float(prices[i]), 2) for i in sign_changes]
        
        # 수익/손실 확률 및 EV (기댓값) 계산 (Log-normal 분포 역추산 적용)
        S0 = current_price or (spot_avg_price if spot_avg_price else 100)
        T_years = days_to_expiry / 365.0 if days_to_expiry > 0 else 0.001
        
        expected_value = 0.0
        win_prob = 0.0
        dp = (price_range[1] - price_range[0]) / num_points
        
        for p, pnl in zip(prices, total_pnl):
            if p <= 0: continue
            
            # Log-normal PDF
            ln_ret = math.log(p / S0)
            d = (ln_ret + 0.5 * volatility**2 * T_years) / (volatility * math.sqrt(T_years))
            pdf = (1.0 / (p * volatility * math.sqrt(2 * math.pi * T_years))) * math.exp(-0.5 * d**2)
            
            prob = pdf * dp
            expected_value += pnl * prob
            if pnl > 0:
                win_prob += prob
                
        # win_prob 보정 (적분 오차 방지)
        win_prob = min(win_prob, 1.0)
        
        return {
            'prices': prices.tolist(),
            'spot_pnl': spot_pnl.tolist(),
            'option_pnl': total_option_pnl.tolist(),
            'total_pnl': total_pnl.tolist(),
            'breakeven_prices': breakevens,
            'max_profit': round(float(total_pnl.max()), 2),
            'max_loss': round(float(total_pnl.min()), 2),
            'option_details': option_details,
            'risk_reward': round(abs(total_pnl.max() / total_pnl.min()), 2) if total_pnl.min() != 0 else float('inf'),
            'win_probability': round(win_prob, 4),
            'expected_value': round(expected_value, 2),
            'expected_value_note': f"EV: ${expected_value:,.2f} (확률기반 승률 {win_prob:.1%})",
        }

    def vix_analysis(self) -> dict:
        """
        VIX 현재 수준 분석 및 해석
        
        Returns:
            {
                'vix': 18.5,
                'level': 'Normal',
                'signal': 'Neutral',
                'interpretation': '...해설...'
            }
        """
        try:
            vix = yf.Ticker("^VIX")
            info = vix.info
            current_vix = info.get('regularMarketPrice') or info.get('currentPrice', 0)
            
            # VIX 역사 데이터
            hist = yf.download("^VIX", period="1y", progress=False)
            if isinstance(hist.columns, pd.MultiIndex):
                hist.columns = hist.columns.get_level_values(0)
            
            vix_percentile = float((hist['Close'] < current_vix).mean() * 100) if not hist.empty else 50
            
            # 수준 해석
            if current_vix < 15:
                level = '🟢 Low (낮음 - 시장 안정)'
                signal = 'Complacency (자만 주의)'
                interpretation = f'VIX {current_vix:.1f}: 시장이 매우 안정적. 역발상으로 하락 리스크 주의.'
            elif current_vix < 20:
                level = '🟡 Normal (보통)'
                signal = 'Neutral'
                interpretation = f'VIX {current_vix:.1f}: 정상 변동성 수준. 일반적인 시장 환경.'
            elif current_vix < 30:
                level = '🟠 Elevated (높음 - 불안)'
                signal = 'Caution (주의)'
                interpretation = f'VIX {current_vix:.1f}: 시장 불안정. 옵션 프리미엄 높음. 헤지 비용 증가.'
            elif current_vix < 40:
                level = '🔴 High (매우 높음 - 공포)'
                signal = 'Opportunity? (역발상 기회)'
                interpretation = f'VIX {current_vix:.1f}: 극도의 공포. 과거 이 수준에서 역발상 매수가 유효했음.'
            else:
                level = '🚨 Extreme (위기 - 패닉)'
                signal = 'Crash Mode (위기 대응)'
                interpretation = f'VIX {current_vix:.1f}: 금융 위기 수준. 2008, 2020 수준. 변동성 극대.'
            
            return {
                'vix': round(current_vix, 2),
                'level': level,
                'signal': signal,
                'interpretation': interpretation,
                'vix_percentile_1y': round(vix_percentile, 1),
                'vix_1y_high': round(float(hist['Close'].max()), 2) if not hist.empty else 0,
                'vix_1y_low': round(float(hist['Close'].min()), 2) if not hist.empty else 0,
                'vix_1y_avg': round(float(hist['Close'].mean()), 2) if not hist.empty else 0,
            }
        except Exception as e:
            print(f"❌ VIX 조회 실패: {e}")
            return {'error': str(e)}

    def futures_basis(
        self,
        spot_price: float,
        futures_price: float,
        days_to_expiry: int,
        rf_rate: float = 0.05,
        dividend_yield: float = 0.0
    ) -> dict:
        """
        선물 베이시스 분석
        
        - Basis = Futures - Spot (양수 = Contango, 음수 = Backwardation)
        - 이론 선물가 = Spot × exp((r - q) × T)
        - Backwardation: 재고 희소, 원자재에서 강세 신호
        - Contango: 정상 상태, 보유 비용 반영
        """
        T = days_to_expiry / 365.0
        theoretical_futures = spot_price * math.exp((rf_rate - dividend_yield) * T)
        basis = futures_price - spot_price
        basis_pct = (basis / spot_price) * 100
        implied_basis_rate = (math.log(futures_price / spot_price) / T) if T > 0 else 0
        mispricing = futures_price - theoretical_futures
        
        structure = 'Contango (정상)' if basis > 0 else 'Backwardation (역조)'
        signal = '중립' if abs(basis_pct) < 0.5 else ('약세 신호 (Backwardation)' if basis < 0 else '강세 기대 (Contango)')
        
        return {
            'spot': spot_price,
            'futures': futures_price,
            'theoretical_futures': round(theoretical_futures, 2),
            'basis': round(basis, 2),
            'basis_pct': round(basis_pct, 3),
            'implied_rate': round(implied_basis_rate * 100, 2),
            'mispricing': round(mispricing, 2),
            'structure': structure,
            'signal': signal,
            'days_to_expiry': days_to_expiry,
        }

    def recommend_protective_put(self, ticker: str, spot_qty: int, spot_price: float) -> dict:
        """
        현물 보유 비중과 연동하여 최대 손실을 제한하는 최적의 풋 매수(Protective Put) 추천
        """
        try:
            # 옵션 체인 정보 로드
            chain_info = self.build_option_chain_summary(ticker)
            if 'error' in chain_info:
                return chain_info
            
            # 현재가 대비 -5% ~ -10% 외가격(OTM) 풋옵션 탐색
            target_strike_min = spot_price * 0.90
            target_strike_max = spot_price * 0.95
            
            puts = pd.DataFrame(chain_info['put_chain'])
            # 행사가(strike)가 target 범위에 있는 것 중 거래량(oi)이 가장 많은 것 추천
            candidates = puts[(puts['strike'] >= target_strike_min) & (puts['strike'] <= target_strike_max)]
            
            if candidates.empty:
                # 범위 내 없으면 가장 가까운 OTM 풋 추천
                candidates = puts[puts['strike'] < spot_price].sort_values(by='strike', ascending=False)
            
            if candidates.empty:
                return {'error': '추천할 풋옵션 행사가를 찾을 수 없습니다.'}
                
            best_put = candidates.iloc[0]
            premium = best_put['iv'] * 100 # 임시 프리미엄 계산 (실제는 ask/bid 사용 권장)
            
            return {
                'ticker': ticker,
                'strategy': 'PROTECTIVE_PUT',
                'recommend_strike': best_put['strike'],
                'cost_per_contract': premium,
                'contracts_needed': math.ceil(spot_qty / 100),
                'max_loss_limited_to': round(spot_price - best_put['strike'] + (premium/100), 2),
                'description': f"주가 {best_put['strike']}원 이하 하락 시 손실 방어. 보험 성격의 매수 전략."
            }
        except Exception as e:
            return {'error': str(e)}

    def get_vix_volatility_strategy(self) -> dict:
        """
        VIX 수준에 따른 매수 전용(Long-Only) 변동성 전략 추천
        """
        vix_data = self.vix_analysis()
        if 'error' in vix_data:
            return vix_data
            
        current_vix = vix_data['vix']
        
        # 전략 결정 로직
        if current_vix < 15:
            # 변동성 저점 -> 조만간 튈 가능성 (Long Call or Straddle Buy)
            strategy = "LONG_CALL / STRADDLE_BUY"
            reason = "VIX가 역사적 저점입니다. 저렴한 프리미엄으로 시장 상방 베팅 또는 변동성 확대에 베팅하기 좋은 시점입니다."
            action = "ATM 콜옵션 매수 고려"
        elif current_vix > 30:
            # 변동성 고점 -> 패닉 구간 (Long Put은 비싸지만 추가 하락 방어 필요 시)
            strategy = "LONG_PUT (HEDGE)"
            reason = "VIX가 급등한 공포 국면입니다. 추가 폭락에 대비한 보험(풋 매수)이 필요할 수 있으나, 프리미엄이 비싸므로 소량 진입 권장."
            action = "OTM 풋옵션 소량 매수 고려"
        else:
            strategy = "WAIT / TREND_FOLLOW"
            reason = "정상 변동성 구간입니다. 특정 방향성 추세 확인 후 매수 진입을 권장합니다."
            action = "관망 또는 섹터별 롱 전략"
            
        return {
            'current_vix': current_vix,
            'vix_level': vix_data['level'],
            'recommended_strategy': strategy,
            'reason': reason,
            'action': action
        }

    def build_option_chain_summary(self, ticker: str) -> dict:
        """
        티커의 옵션 체인 요약 (Yahoo Finance)
        
        - Put-Call Ratio
        - 최대 오픈 인터레스트 행사가 (Pin Risk)
        - 내재변동성 스마일 데이터
        """
        try:
            stock = yf.Ticker(ticker)
            expirations = stock.options
            
            if not expirations:
                return {'error': '옵션 데이터 없음 (한국 주식은 미지원)'}
            
            # 가장 가까운 만기
            nearest_exp = expirations[0]
            chain = stock.option_chain(nearest_exp)
            
            calls = chain.calls
            puts = chain.puts
            
            # Put-Call Ratio (OI 기준)
            total_call_oi = calls['openInterest'].sum()
            total_put_oi = puts['openInterest'].sum()
            pcr = round(total_put_oi / total_call_oi, 3) if total_call_oi > 0 else 0
            
            # 최대 OI 행사가 (Most Pain = Max Pain)
            all_strikes = sorted(set(calls['strike'].tolist() + puts['strike'].tolist()))
            
            # 내재변동성 데이터
            call_ivs = calls[['strike', 'impliedVolatility', 'openInterest']].rename(
                columns={'impliedVolatility': 'iv', 'openInterest': 'oi'}
            ).dropna()
            put_ivs = puts[['strike', 'impliedVolatility', 'openInterest']].rename(
                columns={'impliedVolatility': 'iv', 'openInterest': 'oi'}
            ).dropna()
            
            spot = stock.info.get('regularMarketPrice', 0)
            
            pcr_signal = 'Bearish (Bear 우세)' if pcr > 1.2 else ('Bullish (Bull 우세)' if pcr < 0.7 else 'Neutral')
            
            return {
                'ticker': ticker,
                'nearest_expiry': nearest_exp,
                'spot_price': spot,
                'put_call_ratio': pcr,
                'pcr_signal': pcr_signal,
                'total_call_oi': int(total_call_oi),
                'total_put_oi': int(total_put_oi),
                'call_iv_avg': round(float(call_ivs['iv'].mean()), 3) if not call_ivs.empty else 0,
                'put_iv_avg': round(float(put_ivs['iv'].mean()), 3) if not put_ivs.empty else 0,
                'call_chain': call_ivs.to_dict('records')[:10],
                'put_chain': put_ivs.to_dict('records')[:10],
                'available_expirations': list(expirations[:5]),
            }
        except Exception as e:
            return {'error': str(e)}


# ==========================================
# STANDALONE TEST
# ==========================================
if __name__ == "__main__":
    analyzer = DerivativesAnalyzer()
    
    print("[1] Black-Scholes 콜 옵션...")
    result = analyzer.black_scholes(S=150, K=155, T=30, r=0.05, sigma=0.25, option_type='call')
    print(f"    이론가: ${result['price']}")
    print(f"    Delta: {result['delta']}")
    print(f"    Theta: {result['theta']} (일당 시간가치 감소)")
    print(f"    머니니스: {result['moneyness']}")
    
    print("\n[2] 현물+풋옵션 방어 포지션 시뮬레이션...")
    pnl = analyzer.simulate_portfolio_pnl(
        spot_qty=100,
        spot_avg_price=150,
        options=[
            {'type': 'put_long', 'K': 145, 'premium': 3.5, 'qty': 1}
        ],
        price_range=(120, 185),
        current_price=150,
        volatility=0.25,
        days_to_expiry=30
    )
    print(f"    최대 이익: ${pnl['max_profit']:,.0f}")
    print(f"    최대 손실: ${pnl['max_loss']:,.0f}")
    print(f"    손익분기점: {pnl['breakeven_prices']}")
    print(f"    기댓값(EV): {pnl['expected_value_note']}")
    
    print("\n[3] VIX 분석...")
    vix = analyzer.vix_analysis()
    print(f"    VIX: {vix.get('vix')}")
    print(f"    {vix.get('level')}")
    print(f"    {vix.get('interpretation')}")
