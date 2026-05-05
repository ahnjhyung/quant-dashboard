"""
가치투자 분석 엔진
==================
- DCF (Discounted Cash Flow) 내재가치 계산
- 피오트로스키 F-Score (재무 건전성 9점 만점)
- 종합 가치투자 스크리닝
"""

import yfinance as yf
import pandas as pd
import numpy as np
from typing import Optional


class ValueInvestingAnalyzer:
    """
    가치투자 분석 도구 모음
    
    Usage:
        analyzer = ValueInvestingAnalyzer()
        score = analyzer.piotroski_score("005930.KS")
        intrinsic = analyzer.dcf_valuation("AAPL", fcf=100e9, growth_rate=0.08)
        full = analyzer.full_value_analysis("AAPL")
    """

    def __init__(self):
        pass

    def get_stock_info(self, ticker: str) -> dict:
        """
        Yahoo Finance에서 주식 기본 정보 및 재무 지표 수집
        """
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # 재무제표
            try:
                income = stock.financials
                balance = stock.balance_sheet
                cashflow = stock.cashflow
            except:
                income, balance, cashflow = None, None, None
            
            return {
                'info': info,
                'income': income,
                'balance': balance,
                'cashflow': cashflow,
                'ticker': ticker,
            }
        except Exception as e:
            print(f"❌ 주식 정보 로드 실패 [{ticker}]: {e}")
            return {}

    def dcf_valuation(
        self,
        ticker: str = None,
        fcf: float = None,
        growth_rate_1_5: float = 0.10,
        growth_rate_6_10: float = 0.06,
        terminal_growth: float = 0.03,
        discount_rate: float = 0.10,
        years: int = 10,
        shares_outstanding: float = None,
    ) -> dict:
        """
        DCF (Discounted Cash Flow) 내재가치 계산
        
        Args:
            ticker: 야후파이낸스 티커 (FCF가 None일 때 자동 조회)
            fcf: 최근 연간 잉여현금흐름 (USD)
            growth_rate_1_5: 1-5년 FCF 성장률 (default 10%)
            growth_rate_6_10: 6-10년 FCF 성장률 (default 6%)
            terminal_growth: 터미널 성장률 (default 3%)
            discount_rate: 할인율 = WACC (default 10%)
            years: DCF 예측 기간
            shares_outstanding: 발행 주식수
            
        Returns:
            {
                'intrinsic_value_total': 1.2e12,
                'intrinsic_value_per_share': 73.5,
                'current_price': 150.0,
                'margin_of_safety': 0.51,
                'upside_pct': 105.0,
                ... [yearly projections]
            }
        """
        # 자동 데이터 조회
        current_price = None
        if ticker:
            stock_data = self.get_stock_info(ticker)
            info = stock_data.get('info', {})
            current_price = info.get('currentPrice') or info.get('regularMarketPrice', 0)
            
            if fcf is None:
                # 잉여현금흐름 = 영업CF - CAPEX
                cf = stock_data.get('cashflow')
                if cf is not None and not cf.empty:
                    try:
                        ocf = cf.loc['Operating Cash Flow'].iloc[0] if 'Operating Cash Flow' in cf.index else 0
                        capex = cf.loc['Capital Expenditure'].iloc[0] if 'Capital Expenditure' in cf.index else 0
                        fcf = ocf + capex  # capex는 음수로 표시됨
                    except:
                        fcf = 0
                
            if shares_outstanding is None:
                shares_outstanding = info.get('sharesOutstanding', 1e9)
        
        if not fcf:
            return {'error': 'FCF 데이터 없음. FCF 값을 직접 입력하세요.'}
        
        # DCF 계산
        projected_fcf = []
        pv_fcf = []
        
        for year in range(1, years + 1):
            rate = growth_rate_1_5 if year <= 5 else growth_rate_6_10
            if year == 1:
                fcf_t = fcf * (1 + rate)
            else:
                fcf_t = projected_fcf[-1] * (1 + rate)
            
            projected_fcf.append(fcf_t)
            pv = fcf_t / (1 + discount_rate) ** year
            pv_fcf.append(pv)
        
        # 터미널 가치 (영구 성장 모델)
        terminal_fcf = projected_fcf[-1] * (1 + terminal_growth)
        terminal_value = terminal_fcf / (discount_rate - terminal_growth)
        terminal_pv = terminal_value / (1 + discount_rate) ** years
        
        total_pv = sum(pv_fcf) + terminal_pv
        intrinsic_per_share = total_pv / shares_outstanding if shares_outstanding else 0
        
        margin_of_safety = ((intrinsic_per_share - current_price) / intrinsic_per_share) if (intrinsic_per_share and current_price) else 0
        upside = ((intrinsic_per_share - current_price) / current_price * 100) if (intrinsic_per_share and current_price) else 0
        
        return {
            'ticker': ticker,
            'fcf_base': fcf,
            'intrinsic_value_total': total_pv,
            'intrinsic_value_per_share': round(intrinsic_per_share, 2),
            'current_price': current_price,
            'margin_of_safety': round(margin_of_safety, 3),
            'upside_pct': round(upside, 1),
            'is_undervalued': intrinsic_per_share > (current_price * 1.2) if current_price else False,
            'terminal_value': terminal_pv,
            'sum_pv_fcf': sum(pv_fcf),
            'projected_fcf': projected_fcf,
            'pv_fcf': pv_fcf,
            'parameters': {
                'growth_1_5': growth_rate_1_5,
                'growth_6_10': growth_rate_6_10,
                'terminal_growth': terminal_growth,
                'discount_rate': discount_rate,
            }
        }

    def piotroski_score(self, ticker: str) -> dict:
        """
        피오트로스키 F-Score 계산 (0-9점)
        
        수익성(4점) + 레버리지/유동성(3점) + 효율성(2점) = 9점 만점
        - 8-9점: 강한 매수 신호 (재무 우량주)
        - 0-2점: 강한 매도 신호 (재무 불량)
        """
        stock_data = self.get_stock_info(ticker)
        info = stock_data.get('info', {})
        
        scores = {}
        
        try:
            # === 수익성 (Profitability) ===
            # F1: ROA > 0
            roa = info.get('returnOnAssets', 0) or 0
            scores['F1_ROA_positive'] = roa > 0
            
            # F2: 영업현금흐름(OCF) > 0
            ocf = info.get('operatingCashflow', 0) or 0
            scores['F2_OCF_positive'] = ocf > 0
            
            # F3: ROA 전년 대비 개선 (proxy)
            scores['F3_ROA_improved'] = info.get('returnOnAssets', 0) > 0.03  
            
            # F4: 발생항목 (Accruals = OCF/자산 > ROA)
            total_assets = info.get('totalAssets', 1) or 1
            ocf_roa = ocf / total_assets
            scores['F4_accruals_low'] = ocf_roa > roa
            
            # === 레버리지 / 유동성 ===
            # F5: 장기부채 비율 감소 (proxy)
            debt_to_equity = info.get('debtToEquity', 100) or 100
            scores['F5_leverage_decreased'] = debt_to_equity < 100
            
            # F6: 유동비율 개선
            current_ratio = info.get('currentRatio', 0) or 0
            scores['F6_liquidity_improved'] = current_ratio > 1.5
            
            # F7: 신주 발행 없음 (proxy)
            scores['F7_no_dilution'] = not info.get('lastDividendValue', 0) == 0
            
            # === 효율성 (Operating Efficiency) ===
            # F8: 매출총이익률 개선
            gross_margin = info.get('grossMargins', 0) or 0
            scores['F8_gross_margin_improved'] = gross_margin > 0.2
            
            # F9: 자산회전율 개선
            asset_turnover = info.get('revenuePerShare', 0) / max(info.get('bookValue', 1), 1)
            scores['F9_asset_turnover_improved'] = asset_turnover > 0.5

        except Exception as e:
            print(f"⚠️ 피오트로스키 계산 에러 [{ticker}]: {e}")
        
        score = sum(1 for v in scores.values() if v)
        
        if score >= 8:
            category = 'Strong (강한 매수)'
        elif score >= 6:
            category = 'Good (매수 고려)'
        elif score >= 4:
            category = 'Neutral (중립)'
        else:
            category = 'Weak (매도 주의)'
        
        return {
            'ticker': ticker,
            'score': score,
            'max_score': 9,
            'category': category,
            'details': scores,
            'per': info.get('trailingPE', 0),
            'pbr': info.get('priceToBook', 0),
            'roe': (info.get('returnOnEquity', 0) or 0) * 100,
            'current_ratio': info.get('currentRatio', 0),
            'debt_to_equity': info.get('debtToEquity', 0),
        }

    def full_value_analysis(self, ticker: str, fcf: float = None) -> dict:
        """
        종합 가치투자 분석 및 기댓값(EV) 산출
        PIOTROSKS 스코어와 DCF 안전마진을 조합하여 진입 시의 승률 및 EV를 예측합니다.
        """
        # 1. Piotroski Score 수집
        fscore_data = self.piotroski_score(ticker)
        score = fscore_data.get('score', 0)
        
        # 2. DCF Valuation 수집
        dcf_data = self.dcf_valuation(ticker, fcf=fcf)
        dcf_valid = 'error' not in dcf_data
        upside_pct = dcf_data.get('upside_pct', 0) if dcf_valid else 0
        margin_of_safety = dcf_data.get('margin_of_safety', 0) if dcf_valid else 0
        
        # 3. 승률 추정 (Piotroski Score 및 안전마진 기반)
        base_win_prob = 0.30
        fscore_bonus = score * 0.04
        margin_bonus = min(max(margin_of_safety * 100 / 10 * 0.03, 0), 0.15) if dcf_valid else 0
        
        win_probability = min(base_win_prob + fscore_bonus + margin_bonus, 0.90)
        lose_probability = 1.0 - win_probability
        
        # 4. EV 산출
        avg_profit = max(upside_pct, 15.0) if dcf_valid else 15.0
        avg_loss = 20.0
        
        expected_value_pct = (win_probability * avg_profit) - (lose_probability * avg_loss)
        
        return {
            'ticker': ticker,
            'piotroski_score': score,
            'margin_of_safety': margin_of_safety,
            'upside_pct': upside_pct,
            'win_probability': round(win_probability, 4),
            'avg_profit_pct': round(avg_profit, 2),
            'avg_loss_pct': round(avg_loss, 2),
            'expected_value_pct': round(expected_value_pct, 2),
            'dcf_valid': dcf_valid,
            'fscore_category': fscore_data.get('category', ''),
            'per': fscore_data.get('per', 0),
            'pbr': fscore_data.get('pbr', 0),
            'roe': fscore_data.get('roe', 0)
        }

    def screen_stocks(self, ticker_list: list) -> pd.DataFrame:
        """
        주어진 티커 리스트를 순회하며 가치투자 점수를 산출하고 정렬된 데이터프레임 반환
        """
        results = []
        for ticker in ticker_list:
            try:
                analysis = self.full_value_analysis(ticker)
                results.append(analysis)
            except Exception as e:
                print(f"Error screening {ticker}: {e}")
                continue
        
        df = pd.DataFrame(results)
        if not df.empty:
            # EV 및 스코어 순으로 정렬
            df = df.sort_values(by=['expected_value_pct', 'piotroski_score'], ascending=False)
        return df

# ==========================================
# STANDALONE TEST
# ==========================================
if __name__ == "__main__":
    analyzer = ValueInvestingAnalyzer()
    
    print("[1] 애플 DCF 내재가치 분석...")
    dcf = analyzer.dcf_valuation("AAPL", growth_rate_1_5=0.08, growth_rate_6_10=0.05)
    if 'error' not in dcf:
        print(f"    내재가치/주: ${dcf.get('intrinsic_value_per_share', 0):,.2f}")
        print(f"    현재가격: ${dcf.get('current_price', 0):,.2f}")
        print(f"    안전마진: {dcf.get('margin_of_safety', 0)*100:.1f}%")
    else:
        print(f"    에러: {dcf['error']}")
    
    print("\n[2] 피오트로스키 F-Score (MSFT)...")
    fscore = analyzer.piotroski_score("MSFT")
    print(f"    점수: {fscore['score']}/9 → {fscore['category']}")
    
    print("\n[3] 종합 가치투자 EV 산출 (AAPL)...")
    full_analysis = analyzer.full_value_analysis("AAPL")
    print(f"    추정 승률: {full_analysis['win_probability']*100:.1f}%")
    print(f"    예상 수익/손실: +{full_analysis['avg_profit_pct']:.1f}% / -{full_analysis['avg_loss_pct']:.1f}%")
    print(f"    Expected Value (EV): {full_analysis['expected_value_pct']:.2f}%")


