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
    """

    def __init__(self):
        self._stock_cache = {}

    def get_stock_info(self, ticker: str) -> dict:
        """
        Yahoo Finance에서 주식 기본 정보 및 재무 지표 수집
        """
        if ticker in self._stock_cache:
            return self._stock_cache[ticker]
            
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # 재무제표 (최근 4년)
            try:
                income = stock.financials
                balance = stock.balance_sheet
                cashflow = stock.cashflow
            except:
                income, balance, cashflow = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
            
            result = {
                'info': info,
                'income': income,
                'balance': balance,
                'cashflow': cashflow,
                'ticker': ticker,
            }
            self._stock_cache[ticker] = result
            return result
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
        """
        current_price = 0
        if ticker:
            stock_data = self.get_stock_info(ticker)
            info = stock_data.get('info', {})
            current_price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose', 0)
            
            if fcf is None:
                cf = stock_data.get('cashflow')
                if cf is not None and not cf.empty:
                    try:
                        # Free Cash Flow = Operating Cash Flow - Capital Expenditures
                        ocf = cf.loc['Operating Cash Flow'].iloc[0] if 'Operating Cash Flow' in cf.index else 0
                        capex = cf.loc['Capital Expenditure'].iloc[0] if 'Capital Expenditure' in cf.index else 0
                        fcf = ocf + capex  # Capex는 보통 음수이므로 더함
                        
                        if (fcf is None or fcf <= 0) and 'Free Cash Flow' in cf.index:
                            fcf = cf.loc['Free Cash Flow'].iloc[0]
                    except:
                        fcf = None

            if shares_outstanding is None:
                shares_outstanding = info.get('sharesOutstanding') or info.get('impliedSharesOutstanding')

        if fcf is None or fcf <= 0 or not shares_outstanding:
            return {"error": "Insufficient data for DCF analysis"}

        projections = []
        future_fcf = fcf
        
        for i in range(1, 6):
            future_fcf *= (1 + growth_rate_1_5)
            discounted = future_fcf / ((1 + discount_rate) ** i)
            projections.append({'year': i, 'fcf': future_fcf, 'pv': discounted})
            
        for i in range(6, years + 1):
            future_fcf *= (1 + growth_rate_6_10)
            discounted = future_fcf / ((1 + discount_rate) ** i)
            projections.append({'year': i, 'fcf': future_fcf, 'pv': discounted})
            
        terminal_value = (future_fcf * (1 + terminal_growth)) / (discount_rate - terminal_growth)
        pv_terminal_value = terminal_value / ((1 + discount_rate) ** years)
        
        total_pv = sum(p['pv'] for p in projections) + pv_terminal_value
        intrinsic_value_per_share = total_pv / shares_outstanding
        
        margin_of_safety = (intrinsic_value_per_share - current_price) / intrinsic_value_per_share if intrinsic_value_per_share > 0 else 0
        upside_pct = (intrinsic_value_per_share / current_price - 1) * 100 if current_price > 0 else 0
        
        return {
            'ticker': ticker,
            'intrinsic_value_total': total_pv,
            'intrinsic_value_per_share': intrinsic_value_per_share,
            'current_price': current_price,
            'margin_of_safety': round(margin_of_safety, 4),
            'upside_pct': round(upside_pct, 2),
            'projections': projections,
            'terminal_value': terminal_value,
            'pv_terminal_value': pv_terminal_value,
            'parameters': {
                'growth_rate_1_5': growth_rate_1_5,
                'terminal_growth': terminal_growth,
                'discount_rate': discount_rate
            }
        }

    def piotroski_score(self, ticker: str) -> dict:
        """
        피오트로스키 F-Score 계산 (0-9점)
        """
        stock_data = self.get_stock_info(ticker)
        info = stock_data.get('info', {})
        income = stock_data.get('income')
        balance = stock_data.get('balance')
        cashflow = stock_data.get('cashflow')
        
        scores = {}
        
        def get_metric(df, index_name, year_idx=0):
            if df is not None and not df.empty and index_name in df.index:
                try:
                    val = df.loc[index_name].iloc[year_idx]
                    return float(val) if not pd.isna(val) else 0
                except: return 0
            return 0

        try:
            # === 수익성 (Profitability) ===
            ni = get_metric(income, 'Net Income', 0)
            scores['F1_ROA'] = ni > 0
            
            ocf = get_metric(cashflow, 'Operating Cash Flow', 0)
            scores['F2_CFO'] = ocf > 0
            
            total_assets = get_metric(balance, 'Total Assets', 0)
            total_assets_prev = get_metric(balance, 'Total Assets', 1)
            roa = ni / total_assets if total_assets > 0 else 0
            
            ni_prev = get_metric(income, 'Net Income', 1)
            roa_prev = ni_prev / total_assets_prev if total_assets_prev > 0 else 0
            scores['F3_Delta_ROA'] = roa > roa_prev
            
            scores['F4_Accrual'] = (ocf / total_assets if total_assets > 0 else 0) > roa
            
            # === 레버리지 / 유동성 ===
            lt_debt = get_metric(balance, 'Long Term Debt', 0)
            lt_debt_prev = get_metric(balance, 'Long Term Debt', 1)
            scores['F5_Delta_Leverage'] = lt_debt <= lt_debt_prev
            
            curr_assets = get_metric(balance, 'Current Assets', 0)
            curr_liab = get_metric(balance, 'Current Liabilities', 0)
            current_ratio = curr_assets / curr_liab if curr_liab > 0 else 0
            
            curr_assets_prev = get_metric(balance, 'Current Assets', 1)
            curr_liab_prev = get_metric(balance, 'Current Liabilities', 1)
            current_ratio_prev = curr_assets_prev / curr_liab_prev if curr_liab_prev > 0 else 0
            scores['F6_Delta_Liquidity'] = current_ratio > current_ratio_prev
            
            shares = info.get('sharesOutstanding') or get_metric(balance, 'Ordinary Share Capital', 0)
            shares_prev = get_metric(balance, 'Ordinary Share Capital', 1)
            scores['F7_EQ_Issue'] = shares <= shares_prev if shares_prev > 0 else True
            
            # === 효율성 ===
            gp = get_metric(income, 'Gross Profit', 0)
            rev = get_metric(income, 'Total Revenue', 0)
            gm = gp / rev if rev > 0 else 0
            
            gp_prev = get_metric(income, 'Gross Profit', 1)
            rev_prev = get_metric(income, 'Total Revenue', 1)
            gm_prev = gp_prev / rev_prev if rev_prev > 0 else 0
            scores['F8_Delta_Margin'] = gm > gm_prev
            
            turnover = rev / total_assets if total_assets > 0 else 0
            turnover_prev = rev_prev / total_assets_prev if total_assets_prev > 0 else 0
            scores['F9_Delta_Turnover'] = turnover > turnover_prev

        except Exception as e:
            print(f"Piotroski calculation error for {ticker}: {e}")

        score = sum(1 for v in scores.values() if v)
        
        if score >= 7: category = 'Strong (강한 매수)'
        elif score >= 5: category = 'Good (매수 고려)'
        elif score >= 3: category = 'Neutral (중립)'
        else: category = 'Weak (매도 주의)'
        
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
        """
        fscore_data = self.piotroski_score(ticker)
        score = fscore_data.get('score', 0)
        
        dcf_data = self.dcf_valuation(ticker, fcf=fcf)
        dcf_valid = 'error' not in dcf_data
        upside_pct = dcf_data.get('upside_pct', 0) if dcf_valid else 0
        margin_of_safety = dcf_data.get('margin_of_safety', 0) if dcf_valid else 0
        
        # 승률 추정
        base_win_prob = 0.35
        fscore_bonus = score * 0.05
        margin_bonus = min(max(margin_of_safety * 0.1, 0), 0.20) if dcf_valid else 0
        
        win_probability = min(base_win_prob + fscore_bonus + margin_bonus, 0.90)
        lose_probability = 1.0 - win_probability
        
        avg_profit = max(upside_pct, 15.0) if dcf_valid else 15.0
        avg_loss = 15.0
        
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
        주어진 티커 리스트를 순회하며 가치투자 점수를 산출
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
            df = df.sort_values('expected_value_pct', ascending=False)
        return df
