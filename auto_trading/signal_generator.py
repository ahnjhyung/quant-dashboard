"""
자동매매 신호 생성기
=====================
- 분석 모듈 통합 신호 집계
- 신호 우선순위 및 필터링
- 매매 알림 (콘솔/파일 기록)
- 페이퍼트레이딩 / 실거래 전환 지점
"""

import json
import time
import logging
from datetime import datetime
from pathlib import Path
from analysis.entry_timing import EntryTimingEngine
from analysis.bitcoin_analysis import BitcoinAnalyzer
from analysis.short_squeeze import ShortSqueezeAnalyzer
from analysis.cb_analysis import CBRefixingAnalyzer
from analysis.derivatives import DerivativesAnalyzer

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('auto_trading/signals_log.jsonl', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class SignalGenerator:
    """
    자동매매 신호 생성기
    
    분석 모듈 결과를 통합하여 매매 신호를 생성.
    기본적으로 페이퍼트레이딩 모드로 동작.
    
    Usage:
        gen = SignalGenerator(watchlist=['AAPL', 'TSLA', 'BTC-USD'])
        signals = gen.generate_all_signals()
        gen.save_signals(signals)
    """

    def __init__(
        self,
        watchlist_stocks: list = None,
        watchlist_crypto: list = None,
        paper_trading: bool = True,
    ):
        self.watchlist_stocks = watchlist_stocks or [
            'AAPL', 'MSFT', 'GOOGL', 'NVDA', 'META',
            '005930.KS',  # 삼성전자
            '000660.KS',  # SK하이닉스
        ]
        self.watchlist_crypto = watchlist_crypto or ['BTC-USD', 'ETH-USD']
        self.paper_trading = paper_trading
        
        self.timing_engine = EntryTimingEngine()
        self.btc_analyzer = BitcoinAnalyzer()
        self.squeeze_analyzer = ShortSqueezeAnalyzer()
        self.cb_analyzer = CBRefixingAnalyzer()
        self.derivatives = DerivativesAnalyzer()
        
        # 신호 저장 디렉토리
        Path("auto_trading/signals").mkdir(parents=True, exist_ok=True)
        
        if paper_trading:
            logger.info("📋 페이퍼트레이딩 모드로 실행 중 (실거래 비활성화)")

    def generate_stock_signals(self) -> list:
        """주식 종목 신호 일괄 생성"""
        signals = []
        
        market_regime = self.timing_engine.detect_market_regime()
        
        for ticker in self.watchlist_stocks:
            try:
                result = self.timing_engine.analyze_entry(
                    ticker,
                    asset_class='kr_stock' if '.KS' in ticker else 'us_stock'
                )
                
                entry_type = result.get('final', {}).get('entry_type', 'HOLD')
                
                signal = {
                    'timestamp': datetime.now().isoformat(),
                    'ticker': ticker,
                    'asset_class': 'kr_stock' if '.KS' in ticker else 'us_stock',
                    'signal': entry_type,
                    'price': result.get('price', {}).get('current', 0),
                    'stop_loss': result.get('price', {}).get('stop_loss', 0),
                    'target': result.get('price', {}).get('target', 0),
                    'rsi': result.get('technical', {}).get('rsi', 0),
                    'tech_signal': result.get('technical', {}).get('swing_signal', ''),
                    'confidence': result.get('technical', {}).get('swing_confidence', 0),
                    'market_regime': market_regime.get('regime', ''),
                    'position_size_pct': result.get('position_sizing', {}).get('recommended_pct', 0),
                    'paper_trading': self.paper_trading,
                }
                signals.append(signal)
                logger.info(f"✅ [{ticker}] {entry_type} @ {signal['price']}")
                time.sleep(0.5)  # API 속도 제한
                
            except Exception as e:
                logger.error(f"❌ [{ticker}] 신호 생성 실패: {e}")
        
        return signals

    def generate_crypto_signals(self) -> list:
        """암호화폐 신호 생성"""
        signals = []
        
        try:
            btc_analysis = self.btc_analyzer.btc_comprehensive_analysis()
            overall = btc_analysis.get('overall_assessment', '')
            
            if '강한 매수' in overall:
                btc_signal = 'ENTER'
            elif '매수 관심' in overall:
                btc_signal = 'PARTIAL'
            elif '강한 매도' in overall:
                btc_signal = 'AVOID'
            elif '매도 주의' in overall:
                btc_signal = 'REDUCE'
            else:
                btc_signal = 'HOLD'
            
            signals.append({
                'timestamp': datetime.now().isoformat(),
                'ticker': 'BTC-USD',
                'asset_class': 'crypto',
                'signal': btc_signal,
                'price': btc_analysis.get('current_price', 0),
                'overall_assessment': overall,
                'fear_greed': btc_analysis.get('fear_greed', {}).get('current_value', 0),
                'cycle_phase': btc_analysis.get('halving_cycle', {}).get('cycle_phase', ''),
                'bull_signals': btc_analysis.get('bull_signals', 0),
                'bear_signals': btc_analysis.get('bear_signals', 0),
                'paper_trading': self.paper_trading,
            })
            logger.info(f"✅ [BTC-USD] {btc_signal} - {overall}")
            
        except Exception as e:
            logger.error(f"❌ BTC 신호 생성 실패: {e}")
        
        return signals

    def generate_squeeze_signals(self) -> list:
        """숏스퀴즈 신호 생성 — 워치리스트 전체 스크리닝"""
        signals = []
        try:
            squeeze_results = self.squeeze_analyzer.screen(
                self.watchlist_stocks,
                min_score=40.0,
                include_options=False,
            )
            for r in squeeze_results:
                signal = {
                    'timestamp':      datetime.now().isoformat(),
                    'ticker':         r['ticker'],
                    'asset_class':    'squeeze',
                    'signal':         r['signal'],
                    'price':          r.get('technical', {}).get('current_price', 0),
                    'squeeze_score':  r['squeeze_score'],
                    'level':          r['level'],
                    'summary':        r['summary'],
                    'risk_note':      r['risk_note'],
                    'short_pct_float': r.get('short_metrics', {}).get('short_pct_float', 0),
                    'days_to_cover':  r.get('short_metrics', {}).get('days_to_cover', 0),
                    'paper_trading':  self.paper_trading,
                }
                signals.append(signal)
                logger.info(f"🚨 [{r['ticker']}] SQUEEZE {r['squeeze_score']:.1f}점 | {r['level']}")
        except Exception as e:
            logger.error(f"❌ 숏스퀴즈 신호 생성 실패: {e}")
        return signals

    def generate_cb_signals(self) -> list:
        """CB 리픽싱 기회 스캔 (KR 종목 대상)"""
        signals = []
        kr_stocks = [t for t in self.watchlist_stocks if '.KS' in t or '.KQ' in t]
        
        for ticker in kr_stocks:
            try:
                # KR 주식은 corp_code 관리 필요 (여기선 예시로 mapping logic 필요)
                # 실제 운영 시엔 ticker_to_corp_code 매핑 테이블 활용
                # 임시로 더미/특정 종목만 수행
                if '005930' in ticker: # 삼성전자 예시
                    res = self.cb_analyzer.analyze_refixing_opportunity(ticker, "00126380")
                    if res.get('signal') != 'NONE':
                        signals.append({
                            'timestamp': datetime.now().isoformat(),
                            'ticker': ticker,
                            'asset_class': 'cb_refixing',
                            'signal': res['signal'],
                            'ev': res['expected_value'],
                            'reason': res['reason'],
                            'paper_trading': self.paper_trading,
                        })
            except Exception as e:
                logger.error(f"❌ CB 신호 생성 실패 [{ticker}]: {e}")
        return signals

    def generate_option_buy_signals(self) -> list:
        """옵션 롱(매수) 전용 시그널 생성 (미국 지수/우량주 대상)"""
        signals = []
        us_stocks = [t for t in self.watchlist_stocks if '.KS' not in t]
        
        for ticker in us_stocks:
            try:
                # 변동성(VIX) 및 옵션 체인 분석
                chain = self.derivatives.build_option_chain_summary(ticker)
                if 'error' in chain: continue
                
                # [Long Only Strategy] PCR이 낮고 역발상 매수 기회일 때 콜 매수 고려
                if chain['put_call_ratio'] < 0.6:
                    signals.append({
                        'timestamp': datetime.now().isoformat(),
                        'ticker': ticker,
                        'asset_class': 'option_long',
                        'strategy': 'Call Buy (Bullish)',
                        'signal': 'PARTIAL',
                        'reason': f"높은 강세 심리 (PCR {chain['put_call_ratio']}) 포착",
                        'paper_trading': self.paper_trading,
                    })
            except Exception as e:
                logger.error(f"❌ 옵션 신호 생성 실패 [{ticker}]: {e}")
        return signals

    def generate_all_signals(self) -> dict:
        """모든 자산 신호 통합 생성 (주식 + 암호화폐 + 숏스퀴즈)"""
        logger.info("=" * 50)
        logger.info("🤖 자동매매 신호 생성 시작")
        logger.info("=" * 50)

        stock_signals    = self.generate_stock_signals()
        crypto_signals   = self.generate_crypto_signals()
        squeeze_signals  = self.generate_squeeze_signals()
        cb_signals       = self.generate_cb_signals()
        option_signals   = self.generate_option_buy_signals()

        all_signals = stock_signals + crypto_signals + squeeze_signals + cb_signals + option_signals

        # 강한 신호만 필터
        action_signals = [s for s in all_signals if s.get('signal') in ['ENTER', 'AVOID', 'PARTIAL']]

        summary = {
            'timestamp':      datetime.now().isoformat(),
            'total_scanned':  len(all_signals),
            'action_signals': len(action_signals),
            'enter_count':    sum(1 for s in all_signals if s.get('signal') == 'ENTER'),
            'partial_count':  sum(1 for s in all_signals if s.get('signal') == 'PARTIAL'),
            'avoid_count':    sum(1 for s in all_signals if s.get('signal') == 'AVOID'),
            'hold_count':     sum(1 for s in all_signals if s.get('signal') == 'HOLD'),
            'squeeze_alerts': sum(1 for s in squeeze_signals if s.get('signal') in ['ENTER', 'PARTIAL']),
            'paper_trading':  self.paper_trading,
        }

        logger.info(f"📊 스캔 완료: {summary['total_scanned']}개 | 액션 {summary['action_signals']}개 | 스퀴즈 {summary['squeeze_alerts']}개")

        return {
            'summary':        summary,
            'all_signals':    all_signals,
            'action_signals': action_signals,
            'squeeze_signals': squeeze_signals,
        }

    def save_signals(self, signals_data: dict, filepath: str = None) -> str:
        """신호 결과 저장 (JSON)"""
        if not filepath:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            filepath = f"auto_trading/signals/signals_{ts}.json"
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(signals_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"💾 신호 저장: {filepath}")
        return filepath


if __name__ == "__main__":
    gen = SignalGenerator(
        watchlist_stocks=['AAPL', 'MSFT'],
        paper_trading=True
    )
    signals = gen.generate_all_signals()
    gen.save_signals(signals)
    
    print(f"\n📊 신호 요약:")
    print(f"  스캔: {signals['summary']['total_scanned']}개")
    print(f"  진입: {signals['summary']['enter_count']}개")
    print(f"  부분진입: {signals['summary']['partial_count']}개")
    print(f"  회피: {signals['summary']['avoid_count']}개")
