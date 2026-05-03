"""
가치투자 분석 엔진
==================
- DCF (Discounted Cash Flow) 내재가치 계산
- 그레이엄 넘버 (Benjamin Graham 안전마진 공식)
- 피오트로스키 F-Score (재무 건전성 9점 만점)
- 조엘 그린블라트 마법공식 (Magic Formula)
- 종합 가치투자 스크리닝
"""

import math
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
        ranked = analyzer.magic_formula_rank(["AAPL", "MSFT", "GOOG"])
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

    def graham_number(self, eps: float, book_value_per_share: float) -> float:
        """
        벤저민 그레이엄 넘버 계산
        
        공식: √(22.5 × EPS × BPS)
        
        - 22.5 = PER 15 × PBR 1.5의 곱
        - 결과값이 현재 주가보다 높으면 저평가 신호
        
        Args:
            eps: 주당순이익 (EPS)
            book_value_per_share: 주당순자산 (BPS)
            
        Returns:
            그레이엄 넘버 (float)
        """
        if eps <= 0 or book_value_per_share <= 0:
            return 0.0
        return round(math.sqrt(22.5 * eps * book_value_per_share), 2)

    def piotroski_score(self, ticker: str) -> dict:
        """
        피오트로스키 F-Score 계산 (0-9점)
        
        수익성(4점) + 레버리지/유동성(3점) + 효율성(2점) = 9점 만점
        - 8-9점: 강한 매수 신호 (재무 우량주)
        - 0-2점: 강한 매도 신호 (재무 불량)
        
        Returns:
            {
                'score': 7,
                'category': 'Strong (매수)',
                'details': {
                    'ROA_positive': True,
                    'OCF_positive': True,
                    'ROA_improved': True,
                    'accruals_low': False,
                    ...
                }
            }
        """
        stock_data = self.get_stock_info(ticker)
        info = stock_data.get('info', {})
        income = stock_data.get('income')
        balance = stock_data.get('balance')
        cashflow = stock_data.get('cashflow')
        
        scores = {}
        
        try:
            # === 수익성 (Profitability) ===
            # F1: ROA > 0
            roa = info.get('returnOnAssets', 0) or 0
            scores['F1_ROA_positive'] = roa > 0
            
            # F2: 영업현금흐름(OCF) > 0
            ocf = 0
            if cashflow is not None and not cashflow.empty:
                try:
                    ocf = cashflow.loc['Operating Cash Flow'].iloc[0]
                except:
                    pass
            scores['F2_OCF_positive'] = ocf > 0
            
            # F3: ROA 전년 대비 개선
            # Yahoo Finance는 단일 연도만 제공 → 근사치로 처리
            scores['F3_ROA_improved'] = info.get('returnOnAssets', 0) > 0.03  # proxy
            
            # F4: 발생항목 (Accruals = OCF/자산 > ROA)
            total_assets = info.get('totalAssets', 1)
            total_assets = total_assets if total_assets else 1
            ocf_roa = ocf / total_assets if total_assets else 0
            scores['F4_accruals_low'] = ocf_roa > roa
            
            # === 레버리지 / 유동성 ===
            # F5: 장기부채 비율 감소
            debt_to_equity = info.get('debtToEquity', 100) or 100
            scores['F5_leverage_decreased'] = debt_to_equity < 100  # 100% 이하
            
            # F6: 유동비율 개선
            current_ratio = info.get('currentRatio', 0) or 0
            scores['F6_liquidity_improved'] = current_ratio > 1.5
            
            # F7: 신주 발행 없음
            # 정확한 계산을 위해서는 전년 주식수 필요 → proxy
            scores['F7_no_dilution'] = not info.get('lastDividendValue', 0) == 0  # proxy
            
            # === 효율성 (Operating Efficiency) ===
            # F8: 매출총이익률 개선 (gross margin 양수)
            gross_margin = info.get('grossMargins', 0) or 0
            scores['F8_gross_margin_improved'] = gross_margin > 0.2  # 20% 이상
            
            # F9: 자산회전율 개선
            asset_turnover = info.get('revenuePerShare', 0) / max(info.get('bookValue', 1), 1)
            scores['F9_asset_turnover_improved'] = asset_turnover > 0.5

        except Exception as e:
            print(f"⚠️ 피오트로스키 계산 에러 [{ticker}]: {e}")
        
        score = sum(1 for v in scores.values() if v)
        
        if score >= 8:
            category = '🟢 Strong (강한 매수)'
        elif score >= 6:
            category = '🟡 Good (매수 고려)'
        elif score >= 4:
            category = '🟠 Neutral (중립)'
        else:
            category = '🔴 Weak (매도 주의)'
        
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

    def magic_formula_rank(self, tickers: list) -> list:
        """
        조엘 그린블라트 마법공식 순위
        
        - 자본수익률(ROC) 순위 + 이익수익률(Earnings Yield) 순위 합산
        - 합산 순위가 낮을수록 우량한 저평가 주식
        
        Returns:
            [{'ticker': 'AAPL', 'roc_rank': 3, 'ey_rank': 5, 'combined_rank': 8, ...}]
        """
        results = []
        for ticker in tickers:
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                
                # 이익수익률 = EBIT / Enterprise Value (PER의 역수 개념)
                ebit = info.get('ebitda')
                if ebit is None:
                    # JPM과 같은 금융주는 EBITDA 및 EV가 제공되지 않으므로 PER의 역수를 대용치로 사용
                    per_val = info.get('trailingPE') or info.get('forwardPE') or 0
                    earnings_yield = (1 / per_val) if per_val > 0 else 0
                    ebit = 0
                    ev = 0
                else:
                    ev = info.get('enterpriseValue', 1) or 1
                    earnings_yield = ebit / ev if ev else 0
                
                # 자본수익률(ROC) = EBIT / (순고정자산 + 순운전자본)
                # yfinance에서 totalAssets가 누락되는 경우가 많아 거대한 값이 나오는 버그가 있음.
                # 이를 방지하기 위해 ROA(총자산이익률)로 대체하여 안정적으로 계산합니다.
                roc = info.get('returnOnAssets', 0) or 0
                
                results.append({
                    'ticker': ticker,
                    'earnings_yield': round(earnings_yield * 100, 2),  # 퍼센트로 변환
                    'roc': round(roc * 100, 2),                        # 퍼센트로 변환
                    'per': round(info.get('trailingPE', 0) or 0, 2),
                    'pbr': round(info.get('priceToBook', 0) or 0, 2),
                    'roe': round((info.get('returnOnEquity', 0) or 0) * 100, 2),
                    'market_cap': info.get('marketCap', 0),
                    'ebit': ebit,
                    'enterprise_value': ev,
                })
            except Exception as e:
                print(f"⚠️ Magic Formula 에러 [{ticker}]: {e}")
        
        if not results:
            return []
        
        # 순위 계산
        ey_sorted = sorted(results, key=lambda x: -x['earnings_yield'])
        roc_sorted = sorted(results, key=lambda x: -x['roc'])
        
        ey_rank = {r['ticker']: i+1 for i, r in enumerate(ey_sorted)}
        roc_rank = {r['ticker']: i+1 for i, r in enumerate(roc_sorted)}
        
        for r in results:
            r['ey_rank'] = ey_rank.get(r['ticker'], 999)
            r['roc_rank'] = roc_rank.get(r['ticker'], 999)
            r['combined_rank'] = r['ey_rank'] + r['roc_rank']
        
        return sorted(results, key=lambda x: x['combined_rank'])

    def full_value_analysis(self, ticker: str, fcf: float = None) -> dict:
        """
        종합 가치투자 분석 및 기댓값(EV) 산출
        PIOTROSKS 스코어와 DCF 안전마진을 조합하여 진입 시의 승률 및 EV를 예측합니다.
        
        Returns:
            {
                'ticker': 'AAPL',
                'expected_value_pct': 15.3,
                'win_probability': 0.65, ...
            }
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
        # 기본 승률을 30%로 설정 (장기 투자의 불확실성 반영)
        # F-score 1점당 +4% (Max +36%)
        # 안전마진 10%당 +3% (Max +15%)
        base_win_prob = 0.30
        fscore_bonus = score * 0.04
        margin_bonus = min(max(margin_of_safety * 100 / 10 * 0.03, 0), 0.15) if dcf_valid else 0
        
        win_probability = min(base_win_prob + fscore_bonus + margin_bonus, 0.90)
        lose_probability = 1.0 - win_probability
        
        # 4. EV 산출
        # avg_profit: 내재가치 도달 시의 수익률 (안전하게 최소 15% 적용)
        # avg_loss: 펀더멘탈 훼손 시 손절 라인 (-20% 설정)
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
            'fscore_category': fscore_data.get('category', '')
        }

    def value_screen(self, tickers: list) -> list:
        """
        가치투자 종합 스크리닝 (100점 만점 가중치 연속 스코어)

        핵심 지표별 가중치 배분:
        - ROE (수익성) : 30% (가장 중요)
        - PER (수익가치) : 25% (이익 대비 저평가)
        - PBR (자산가치) : 20% (자산 대비 저평가)
        - D/E (재무건전성): 15% (안전성)
        - 배당률 (인컴) : 10% (현금흐름)

        Returns:
            종목 리스트 (score 기준 내림차순 정렬)
        """
        raw_data = []
        for ticker in tickers:
            try:
                stock = yf.Ticker(ticker)
                info = stock.info

                per = info.get('trailingPE') or info.get('forwardPE')
                pbr = info.get('priceToBook')
                roe = info.get('returnOnEquity')
                debt_to_equity = info.get('debtToEquity')
                dividend_yield = info.get('dividendYield')

                raw_data.append({
                    'ticker': ticker,
                    'per': per if per and per > 0 else None,
                    'pbr': pbr if pbr and pbr > 0 else None,
                    'roe': (roe * 100) if roe else None,
                    'debt_to_equity': debt_to_equity if debt_to_equity is not None else None,
                    'dividend_yield': (dividend_yield * 100) if dividend_yield else 0.0,
                    'market_cap': info.get('marketCap', 0),
                    'name': info.get('longName', ticker),
                    'sector': info.get('sector', ''),
                    'current_price': info.get('currentPrice', 0),
                    'target_price': info.get('targetMeanPrice', 0),
                })
            except Exception as e:
                print(f"⚠️ 스크리닝 에러 [{ticker}]: {e}")

        if not raw_data:
            return []

        # ── 가중치 기반 스코어 계산 (합계 100점) ──
        results = []
        for item in raw_data:
            scores = {}
            breakdown = {}

            # 1) PER 점수 (25점 만점, 수익가치)
            per = item['per']
            if per and 0 < per < 200:
                if per <= 10:
                    scores['per'] = 25
                elif per <= 15:
                    scores['per'] = 25 - (per - 10) * 2  # 15~25점
                elif per <= 25:
                    scores['per'] = 15 - (per - 15) * 1  # 5~15점
                elif per <= 60:
                    scores['per'] = max(0, 5 - (per - 25) * 0.14)
                else:
                    scores['per'] = 0
                breakdown['PER'] = f"{per:.1f} → {scores['per']:.1f}/25점"
            else:
                scores['per'] = 0
                breakdown['PER'] = "N/A → 0/25점"

            # 2) PBR 점수 (20점 만점, 자산가치)
            pbr = item['pbr']
            if pbr and 0 < pbr < 100:
                if pbr <= 1.0:
                    scores['pbr'] = 20
                elif pbr <= 1.5:
                    scores['pbr'] = 20 - (pbr - 1.0) * 10  # 15~20점
                elif pbr <= 3.0:
                    scores['pbr'] = 15 - (pbr - 1.5) * 6  # 6~15점
                elif pbr <= 10.0:
                    scores['pbr'] = max(0, 6 - (pbr - 3.0) * 0.86)
                else:
                    scores['pbr'] = 0
                breakdown['PBR'] = f"{pbr:.2f} → {scores['pbr']:.1f}/20점"
            else:
                scores['pbr'] = 0
                breakdown['PBR'] = "N/A → 0/20점"

            # 3) ROE 점수 (30점 만점, 수익성)
            roe = item['roe']
            if roe is not None:
                if roe >= 25:
                    scores['roe'] = 30
                elif roe >= 15:
                    scores['roe'] = 20 + (roe - 15) * 1.0  # 20~30점
                elif roe >= 8:
                    scores['roe'] = 10 + (roe - 8) * 1.42  # 10~20점
                elif roe >= 0:
                    scores['roe'] = roe * 1.25  # 0~10점
                else:
                    scores['roe'] = 0
                breakdown['ROE'] = f"{roe:.1f}% → {scores['roe']:.1f}/30점"
            else:
                scores['roe'] = 0
                breakdown['ROE'] = "N/A → 0/30점"

            # 4) 재무건전성 (15점 만점, 안전성)
            de = item['debt_to_equity']
            if de is not None and de >= 0:
                if de <= 30:
                    scores['debt'] = 15
                elif de <= 50:
                    scores['debt'] = 15 - (de - 30) * 0.25  # 10~15점
                elif de <= 100:
                    scores['debt'] = 10 - (de - 50) * 0.12  # 4~10점
                elif de <= 200:
                    scores['debt'] = max(0, 4 - (de - 100) * 0.04)
                else:
                    scores['debt'] = 0
                breakdown['D/E'] = f"{de:.1f}% → {scores['debt']:.1f}/15점"
            else:
                scores['debt'] = 5  # 데이터 없으면 중립
                breakdown['D/E'] = "N/A → 5/15점(중립)"

            # 5) 배당 점수 (10점 만점, 현금흐름)
            div = item['dividend_yield']
            if div > 0:
                if div >= 4.0:
                    scores['dividend'] = 10
                elif div >= 2.0:
                    scores['dividend'] = 6 + (div - 2.0) * 2  # 6~10점
                elif div >= 1.0:
                    scores['dividend'] = 3 + (div - 1.0) * 3  # 3~6점
                else:
                    scores['dividend'] = div * 3  # 0~3점
                breakdown['배당'] = f"{div:.2f}% → {scores['dividend']:.1f}/10점"
            else:
                scores['dividend'] = 0
                breakdown['배당'] = "0% → 0/10점"

            total_score = round(sum(scores.values()), 1)

            # 등급 부여
            if total_score >= 80:
                grade = "S"
            elif total_score >= 65:
                grade = "A"
            elif total_score >= 50:
                grade = "B"
            elif total_score >= 35:
                grade = "C"
            else:
                grade = "D"

            results.append({
                'ticker': item['ticker'],
                'name': item['name'],
                'score': total_score,
                'grade': grade,
                'per': round(per, 1) if per and per < 9999 else None,
                'pbr': round(pbr, 2) if pbr and pbr < 9999 else None,
                'roe': round(roe, 1) if roe is not None else None,
                'debt_to_equity': round(de, 1) if de is not None else None,
                'dividend_yield': round(div, 2),
                'sector': item['sector'],
                'breakdown': breakdown,
                'scores_detail': scores,
            })

        return sorted(results, key=lambda x: -x['score'])

# ==========================================
# STANDALONE TEST
# ==========================================
if __name__ == "__main__":
    analyzer = ValueInvestingAnalyzer()
    
    print("[1] 애플 DCF 내재가치 분석...")
    dcf = analyzer.dcf_valuation("AAPL", growth_rate_1_5=0.08, growth_rate_6_10=0.05)
    print(f"    내재가치/주: ${dcf.get('intrinsic_value_per_share', 0):,.2f}")
    print(f"    현재가격: ${dcf.get('current_price', 0):,.2f}")
    print(f"    안전마진: {dcf.get('margin_of_safety', 0)*100:.1f}%")
    
    print("\n[2] 그레이엄 넘버 계산...")
    gn = analyzer.graham_number(eps=6.5, book_value_per_share=4.0)
    print(f"    Graham Number (EPS=6.5, BPS=4.0): ${gn}")
    
    print("\n[3] 피오트로스키 F-Score (MSFT)...")
    fscore = analyzer.piotroski_score("MSFT")
    print(f"    점수: {fscore['score']}/9 → {fscore['category']}")
    
    print("\n[4] 종합 가치투자 EV 산출 (AAPL)...")
    full_analysis = analyzer.full_value_analysis("AAPL", fcf=100e9)
    print(f"    추정 승률: {full_analysis['win_probability']*100:.1f}%")
    print(f"    예상 수익/손실: +{full_analysis['avg_profit_pct']:.1f}% / -{full_analysis['avg_loss_pct']:.1f}%")
    print(f"    Expected Value (EV): {full_analysis['expected_value_pct']:.2f}%")

