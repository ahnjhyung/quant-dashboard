"""
포지션 관리자
==============
- 현재 포지션 추적 (페이퍼트레이딩)
- 손절/익절 조건 모니터링
- 포지션 P&L 계산
- 리스크 한도 관리 (계좌 대비 %)
"""

import json
import logging
from datetime import datetime
from pathlib import Path


logger = logging.getLogger(__name__)

POSITION_FILE = "auto_trading/positions.json"


class PositionManager:
    """
    포지션 관리자 (페이퍼트레이딩 기본)
    
    Usage:
        pm = PositionManager(total_capital=10_000_000)
        pm.open_position('AAPL', qty=10, entry_price=150, stop=140, target=170)
        pm.update_prices({'AAPL': 155})
        print(pm.get_summary())
    """

    MAX_POSITION_PCT = 0.25  # 단일 종목 최대 25%
    MAX_TOTAL_RISK_PCT = 0.10  # 전체 계좌 최대 리스크 10%

    def __init__(self, total_capital: float = 10_000_000, paper_trading: bool = True):
        self.total_capital = total_capital
        self.paper_trading = paper_trading
        self.positions = {}
        self.trade_history = []
        
        Path("auto_trading").mkdir(parents=True, exist_ok=True)
        self._load_positions()
        
        logger.info(f"💼 포지션 관리자 초기화 | 자본금: ₩{total_capital:,.0f} | {'페이퍼' if paper_trading else '실거래'}")

    def _load_positions(self):
        """저장된 포지션 불러오기"""
        try:
            if Path(POSITION_FILE).exists():
                with open(POSITION_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.positions = data.get('positions', {})
                    self.trade_history = data.get('history', [])
                logger.info(f"📂 포지션 불러오기 완료: {len(self.positions)}개")
        except Exception as e:
            logger.warning(f"포지션 파일 불러오기 실패: {e}")
            self.positions = {}

    def _save_positions(self):
        """포지션 저장"""
        with open(POSITION_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'positions': self.positions,
                'history': self.trade_history[-100:],  # 최근 100건
                'last_updated': datetime.now().isoformat(),
                'total_capital': self.total_capital,
                'paper_trading': self.paper_trading,
            }, f, ensure_ascii=False, indent=2)

    def open_position(
        self,
        ticker: str,
        qty: int,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        note: str = ''
    ) -> dict:
        """
        포지션 오픈
        
        리스크 한도 초과 시 자동 거부.
        """
        position_value = qty * entry_price
        position_pct = position_value / self.total_capital
        
        # 리스크 한도 체크
        if position_pct > self.MAX_POSITION_PCT:
            msg = f"⚠️ [{ticker}] 포지션 한도 초과 ({position_pct:.1%} > {self.MAX_POSITION_PCT:.0%})"
            logger.warning(msg)
            return {'success': False, 'reason': msg}
        
        if ticker in self.positions:
            logger.warning(f"⚠️ [{ticker}] 이미 포지션 보유 중")
            return {'success': False, 'reason': '이미 포지션 존재'}
        
        position = {
            'ticker': ticker,
            'qty': qty,
            'entry_price': entry_price,
            'current_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'position_value': round(position_value, 2),
            'unrealized_pnl': 0,
            'unrealized_pnl_pct': 0,
            'open_time': datetime.now().isoformat(),
            'note': note,
            'paper_trading': self.paper_trading,
        }
        
        self.positions[ticker] = position
        self._save_positions()
        
        logger.info(f"✅ [{ticker}] 포지션 오픈: {qty}주 @ ₩{entry_price:,.0f} (Stop: {stop_loss}, Target: {take_profit})")
        return {'success': True, 'position': position}

    def close_position(self, ticker: str, close_price: float, reason: str = 'Manual') -> dict:
        """포지션 청산"""
        if ticker not in self.positions:
            return {'success': False, 'reason': '포지션 없음'}
        
        pos = self.positions[ticker]
        pnl = (close_price - pos['entry_price']) * pos['qty']
        pnl_pct = (close_price - pos['entry_price']) / pos['entry_price'] * 100
        
        trade_record = {
            **pos,
            'close_price': close_price,
            'close_time': datetime.now().isoformat(),
            'realized_pnl': round(pnl, 2),
            'realized_pnl_pct': round(pnl_pct, 2),
            'close_reason': reason,
        }
        
        self.trade_history.append(trade_record)
        del self.positions[ticker]
        self._save_positions()
        
        emoji = '🟢' if pnl >= 0 else '🔴'
        logger.info(f"{emoji} [{ticker}] 청산 | 손익: ₩{pnl:+,.0f} ({pnl_pct:+.2f}%) | 사유: {reason}")
        return {'success': True, 'trade': trade_record}

    def update_prices(self, price_dict: dict) -> list:
        """현재가 업데이트 및 손절/익절 체크"""
        triggered = []
        
        for ticker, price in price_dict.items():
            if ticker not in self.positions:
                continue
            
            pos = self.positions[ticker]
            pos['current_price'] = price
            pos['unrealized_pnl'] = round((price - pos['entry_price']) * pos['qty'], 2)
            pos['unrealized_pnl_pct'] = round((price - pos['entry_price']) / pos['entry_price'] * 100, 2)
            
            # 손절 체크
            if price <= pos['stop_loss']:
                result = self.close_position(ticker, price, reason='Stop Loss 손절')
                triggered.append({'ticker': ticker, 'type': 'STOP_LOSS', 'price': price, **result})
            
            # 익절 체크
            elif price >= pos['take_profit']:
                result = self.close_position(ticker, price, reason='Take Profit 익절')
                triggered.append({'ticker': ticker, 'type': 'TAKE_PROFIT', 'price': price, **result})
        
        self._save_positions()
        return triggered

    def get_summary(self) -> dict:
        """포트폴리오 현황 요약"""
        total_invested = sum(p['position_value'] for p in self.positions.values())
        total_unrealized_pnl = sum(p['unrealized_pnl'] for p in self.positions.values())
        
        # 과거 거래 성과
        if self.trade_history:
            total_realized = sum(t.get('realized_pnl', 0) for t in self.trade_history)
            win_trades = [t for t in self.trade_history if t.get('realized_pnl', 0) > 0]
            win_rate = len(win_trades) / len(self.trade_history) * 100
        else:
            total_realized = 0
            win_rate = 0
        
        cash = self.total_capital - total_invested + total_realized
        
        return {
            'total_capital': self.total_capital,
            'cash': round(cash, 2),
            'invested': round(total_invested, 2),
            'invested_pct': round(total_invested / self.total_capital * 100, 1),
            'unrealized_pnl': round(total_unrealized_pnl, 2),
            'total_realized_pnl': round(total_realized, 2),
            'position_count': len(self.positions),
            'total_trades': len(self.trade_history),
            'win_rate': round(win_rate, 1),
            'positions': list(self.positions.values()),
            'paper_trading': self.paper_trading,
        }


if __name__ == "__main__":
    pm = PositionManager(total_capital=10_000_000, paper_trading=True)
    
    pm.open_position('AAPL', qty=10, entry_price=150, stop_loss=140, take_profit=175, note='기술적 매수')
    pm.update_prices({'AAPL': 152})
    
    summary = pm.get_summary()
    print(f"투자금: ₩{summary['invested']:,.0f} ({summary['invested_pct']}%)")
    print(f"미실현 손익: ₩{summary['unrealized_pnl']:+,.0f}")
    print(f"포지션 수: {summary['position_count']}개")
