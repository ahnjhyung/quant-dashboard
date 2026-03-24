"""
paper_trader.py - KRW 크로스 차익 페이퍼 트레이딩 시뮬레이터 v2
==============================================================
[현실화 개선사항 v2]
  1. 호가(Orderbook) 기반 실체결가 - Best Ask(매수) / Best Bid(매도) 사용
  2. 체결 지연 시뮬 - 0.3~0.8s 딜레이 후 가격 재조회 + "드리프트" 반영
  3. API 오류 시뮬 - 5% 확률 주문 실패, 1회 재시도
  4. 드로다운 추적 - 최고점 대비 낙폭 / 15% 이상 시 자동 정지
  5. 쿨다운 - 코인별 마지막 체결 후 60초 재거래 금지
  6. Kelly 포지션 사이징 - EV/분산 기반 최적 투자금 계산
  7. 멀티코인 EV 우선순위 - EV 높은 신호 먼저 실행

사용법:
    python -m hft_arb.paper_trader
    python -m hft_arb.paper_trader --capital 5000000 --interval 30
    python -m hft_arb.paper_trader --capital 5000000 --interval 30 --use-kelly
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from hft_arb.ev_engine import EVEngine, KRW_CROSS_THRESHOLD
from hft_arb.krw_cross_scanner import KRWCrossScanner

logger = logging.getLogger(__name__)

# ── 수수료 파라미터 ─────────────────────────────────────────────
FEE_UPBIT   = 0.0005   # 업비트 taker 0.05%
FEE_BITHUMB = 0.0025   # 빗썸 taker 0.25%
BASE_SLIPPAGE = 0.0010  # 기본 슬리피지 (호가 조회 실패 시 fallback)
TOTAL_BASE_FEE = FEE_UPBIT + FEE_BITHUMB  # 0.30% (슬리피지는 동적)

# ── 현실화 파라미터 ─────────────────────────────────────────────
API_FAIL_PROB      = 0.05   # 5% API 실패 확률
COOLDOWN_SEC       = 60     # 코인별 쿨다운 (초)
MAX_DRAWDOWN_STOP  = 0.15   # 15% 드로다운 시 자동 정지
REBALANCE_FEE      = 0.0005 # 재배분(온체인 전송) 비용 0.05%
EXEC_DELAY_LOW     = 0.3    # 체결 지연 최솟값 (초)
EXEC_DELAY_HIGH    = 0.8    # 체결 지연 최댓값 (초)

# ── Kelly 파라미터 ──────────────────────────────────────────────
KELLY_FRACTION     = 0.25   # 분수 Kelly (안전계수)
KELLY_MIN_KRW      = 50_000   # 최소 투자금
KELLY_MAX_RATIO    = 0.30   # 최대 per_side의 30%


# ─────────────────────────────────────────────────────────────────
# 데이터 클래스
# ─────────────────────────────────────────────────────────────────

@dataclass
class PaperTrade:
    """단일 페이퍼 트레이드 기록."""
    ts: float
    symbol: str
    direction: str
    # 신호 당시 가격
    p_upbit_signal: float
    p_bithumb_signal: float
    # 실제 체결가 (호가+지연 반영)
    p_buy_fill: float
    p_sell_fill: float
    spread_pct: float        # 신호 스프레드 %
    actual_slippage_pct: float  # 실제 슬리피지 %
    trade_krw: float
    gross_profit: float
    fee: float
    net_profit: float
    ev_pct: float
    exec_delay_ms: int       # 체결 지연 (ms)
    api_retry: bool          # API 재시도 여부


@dataclass
class PaperPortfolio:
    """페이퍼 트레이딩 포트폴리오 상태."""
    upbit_krw: float
    bithumb_krw: float
    initial_total: float = 0.0
    trades: list[PaperTrade] = field(default_factory=list)
    rebalance_count: int = 0
    rebalance_cost_total: float = 0.0
    api_fail_count: int = 0
    api_retry_count: int = 0
    _peak_krw: float = 0.0   # 드로다운 계산용 최고점

    def __post_init__(self):
        self.initial_total = self.upbit_krw + self.bithumb_krw
        self._peak_krw = self.initial_total

    @property
    def total_krw(self) -> float:
        return self.upbit_krw + self.bithumb_krw

    @property
    def total_profit(self) -> float:
        return sum(t.net_profit for t in self.trades)

    @property
    def win_count(self) -> int:
        return sum(1 for t in self.trades if t.net_profit > 0)

    @property
    def win_rate(self) -> float:
        return self.win_count / len(self.trades) if self.trades else 0.0

    @property
    def total_return_pct(self) -> float:
        return self.total_profit / self.initial_total * 100 if self.initial_total else 0.0

    @property
    def avg_profit_per_trade(self) -> float:
        return self.total_profit / len(self.trades) if self.trades else 0.0

    @property
    def avg_slippage_pct(self) -> float:
        if not self.trades:
            return 0.0
        return sum(t.actual_slippage_pct for t in self.trades) / len(self.trades)

    @property
    def drawdown_pct(self) -> float:
        """현재 드로다운 % (최고점 대비)."""
        if self._peak_krw <= 0:
            return 0.0
        return (self._peak_krw - self.total_krw) / self._peak_krw * 100

    def update_peak(self):
        """현재 자본이 최고점이면 갱신."""
        if self.total_krw > self._peak_krw:
            self._peak_krw = self.total_krw


# ─────────────────────────────────────────────────────────────────
# 호가 조회 헬퍼
# ─────────────────────────────────────────────────────────────────

def _get_upbit_orderbook(symbol: str) -> dict | None:
    """업비트 호가창 조회 → {ask: 최우선 매도호가, bid: 최우선 매수호가}."""
    try:
        import pyupbit
        ob = pyupbit.get_orderbook(f"KRW-{symbol}")
        if not ob:
            return None
        units = ob[0].get("orderbook_units", [])
        if not units:
            return None
        return {
            "ask": units[0]["ask_price"],   # 매수자가 내야 하는 최저 매도호가
            "bid": units[0]["bid_price"],   # 매도자가 받는 최고 매수호가
            "ask_size": units[0]["ask_size"],
            "bid_size": units[0]["bid_size"],
        }
    except Exception as e:
        logger.debug(f"[OB] 업비트 {symbol} 호가 조회 실패: {e}")
        return None


def _get_bithumb_orderbook(symbol: str) -> dict | None:
    """빗썸 호가창 조회 → {ask: 최우선 매도호가, bid: 최우선 매수호가}."""
    try:
        import pybithumb
        ob = pybithumb.get_orderbook(symbol)
        if not ob:
            return None
        # pybithumb 반환: DataFrame 또는 dict
        if hasattr(ob, 'iloc'):
            # DataFrame 형태
            asks = ob[ob['type'] == 'ask']
            bids = ob[ob['type'] == 'bid']
            if asks.empty or bids.empty:
                return None
            return {
                "ask": float(asks['price'].min()),
                "bid": float(bids['price'].max()),
            }
        elif isinstance(ob, dict):
            data = ob.get('data', {})
            asks = data.get('asks', [])
            bids = data.get('bids', [])
            if not asks or not bids:
                return None
            return {
                "ask": float(asks[0][0]),
                "bid": float(bids[0][0]),
            }
    except Exception as e:
        logger.debug(f"[OB] 빗썸 {symbol} 호가 조회 실패: {e}")
        return None


def _get_current_price(symbol: str, exchange: str) -> float | None:
    """현재가 조회 (호가 조회 실패 시 fallback)."""
    try:
        if exchange == "upbit":
            import pyupbit
            return float(pyupbit.get_current_price(f"KRW-{symbol}"))
        else:
            import pybithumb
            return float(pybithumb.get_current_price(symbol))
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────
# 메인 시뮬레이터
# ─────────────────────────────────────────────────────────────────

class PaperTrader:
    """
    KRW 크로스 차익 페이퍼 트레이딩 시뮬레이터 (현실화 v2).

    Args:
        per_side_krw: 업비트/빗썸 각 초기 자본 (원)
        scan_interval: 스캔 주기 (초)
        use_kelly: True=Kelly 포지션 사이징, False=고정 80%
        fixed_trade_krw: use_kelly=False 시 고정 투자금 (None=per_side의 80%)
    """

    def __init__(
        self,
        per_side_krw: float = 5_000_000,
        scan_interval: float = 30.0,
        use_kelly: bool = False,
        fixed_trade_krw: float | None = None,
    ) -> None:
        self.engine = EVEngine(fx_rate_krw=1500.0)
        self.scanner = KRWCrossScanner(self.engine)
        self.scan_interval = scan_interval
        self.use_kelly = use_kelly

        self.portfolio = PaperPortfolio(
            upbit_krw=per_side_krw,
            bithumb_krw=per_side_krw,
        )

        self._fixed_trade_krw = fixed_trade_krw or per_side_krw * 0.80
        self._cooldown: dict[str, float] = {}   # symbol -> last_trade_ts
        self._scan_count = 0
        self._start_time = time.time()
        self._stopped = False   # 드로다운 정지 플래그

    # ── 현실화 헬퍼 ───────────────────────────────────────────────

    def _check_cooldown(self, symbol: str) -> bool:
        """True=쿨다운 중 (거래 불가)."""
        last = self._cooldown.get(symbol, 0)
        elapsed = time.time() - last
        return elapsed < COOLDOWN_SEC

    def _update_cooldown(self, symbol: str) -> None:
        self._cooldown[symbol] = time.time()

    def _kelly_position_size(self, ev_pct: float, spread_pct: float) -> float:
        """
        Kelly Criterion 기반 최적 포지션 크기 계산.

        f = EV_pct / (spread_pct^2)  (단순 Kelly 근사)
        실제 투자금 = f * KELLY_FRACTION * 가용자본
        """
        if spread_pct <= 0:
            return self._fixed_trade_krw
        kelly_f = ev_pct / (spread_pct ** 2)
        kelly_f = max(0.01, min(kelly_f, 1.0))   # 0~100% 클램프
        available = min(self.portfolio.upbit_krw, self.portfolio.bithumb_krw)
        size = kelly_f * KELLY_FRACTION * available
        size = max(KELLY_MIN_KRW, min(size, available * KELLY_MAX_RATIO))
        return size

    def _simulate_api_error(self) -> tuple[bool, bool]:
        """
        API 오류 시뮬레이션.

        Returns:
            (성공여부, 재시도여부)
        """
        if random.random() < API_FAIL_PROB:
            # 첫 시도 실패 → 재시도
            self.portfolio.api_fail_count += 1
            if random.random() < API_FAIL_PROB:
                # 재시도도 실패
                return False, True
            return True, True   # 재시도 성공
        return True, False   # 첫 시도 성공

    async def _get_orderbook_fill_prices(
        self,
        symbol: str,
        buy_exchange: str,
    ) -> tuple[float | None, float | None, float, float]:
        """
        호가창 기반 실제 체결가 및 잔량 조회.

        Returns:
            (매수체결가, 매도체결가, 슬리피지%, 최대가능볼륨KRW)
        """
        upbit_ob, bithumb_ob = await asyncio.gather(
            asyncio.to_thread(_get_upbit_orderbook, symbol),
            asyncio.to_thread(_get_bithumb_orderbook, symbol),
        )

        if buy_exchange == "upbit":
            p_buy  = upbit_ob["ask"]   if upbit_ob   else _get_current_price(symbol, "upbit")
            p_sell = bithumb_ob["bid"] if bithumb_ob  else _get_current_price(symbol, "bithumb")
            # 최대 가용 볼륨 = Min(업비트 매도 잔량비용, 빗썸 매수 잔량비용)
            buy_vol  = (upbit_ob["ask"] * upbit_ob["ask_size"]) if upbit_ob else float('inf')
            sell_vol = (bithumb_ob["bid"] * bithumb_ob["bid_size"]) if bithumb_ob else float('inf')
        else:  # buy bithumb
            p_buy  = bithumb_ob["ask"] if bithumb_ob  else _get_current_price(symbol, "bithumb")
            p_sell = upbit_ob["bid"]   if upbit_ob    else _get_current_price(symbol, "upbit")
            # 최대 가용 볼륨 = Min(빗썸 매도 잔량비용, 업비트 매수 잔량비용)
            buy_vol  = (bithumb_ob["ask"] * bithumb_ob["ask_size"]) if bithumb_ob else float('inf')
            sell_vol = (upbit_ob["bid"] * upbit_ob["bid_size"]) if upbit_ob else float('inf')

        top_level_vol_krw = min(buy_vol, sell_vol)

        if p_buy is None or p_sell is None:
            return None, None, BASE_SLIPPAGE, top_level_vol_krw

        if upbit_ob and bithumb_ob:
            upbit_spread = (upbit_ob["ask"] - upbit_ob["bid"]) / upbit_ob["bid"]
            bithumb_spread = (bithumb_ob["ask"] - bithumb_ob["bid"]) / bithumb_ob["bid"]
            actual_slippage = (upbit_spread + bithumb_spread) / 2
        else:
            actual_slippage = BASE_SLIPPAGE

        return p_buy, p_sell, actual_slippage, top_level_vol_krw

    async def _execute_with_delay(
        self,
        symbol: str,
        buy_exchange: str,
        p_buy_signal: float,
        p_sell_signal: float,
    ) -> tuple[float, float, float, int, float]:
        """
        체결 지연 시뮬 + 가격 드리프트 반영.

        Returns:
            (매수체결가, 매도체결가, 슬리피지%, 지연ms, 최대가용볼륨)
        """
        delay = random.uniform(EXEC_DELAY_LOW, EXEC_DELAY_HIGH)
        await asyncio.sleep(delay)

        p_buy_fill, p_sell_fill, slip, top_vol = await self._get_orderbook_fill_prices(
            symbol, buy_exchange
        )

        if p_buy_fill is None:
            p_buy_fill  = p_buy_signal  * (1 + BASE_SLIPPAGE)
            p_sell_fill = p_sell_signal * (1 - BASE_SLIPPAGE)
            slip = BASE_SLIPPAGE
            top_vol = float('inf')

        return p_buy_fill, p_sell_fill, slip, int(delay * 1000), top_vol

    def _auto_rebalance(self, trade_size: float) -> bool:
        """
        자동 재배분. True=재배분 실행됨, False=자본 부족으로 불가.

        실제 거래에서는 코인 온체인 이전 필요 → 비용 REBALANCE_FEE 차감.
        """
        p = self.portfolio
        total = p.total_krw
        cost  = total * REBALANCE_FEE
        after = (total - cost) / 2

        if after < trade_size:
            return False

        p.upbit_krw   = after
        p.bithumb_krw = after
        p.rebalance_count     += 1
        p.rebalance_cost_total += cost
        print(
            f"  [재배분 #{p.rebalance_count}] 총 {total:,.0f}원 -> 각 {after:,.0f}원 "
            f"(비용 {cost:,.0f}원 / 실제: 온체인 이전 필요)"
        )
        return True

    # ── 메인 트레이드 실행 ────────────────────────────────────────

    async def _execute_paper_trade(self, signal) -> PaperTrade | None:
        """신호 기반 페이퍼 트레이드 실행 (현실화 로직 포함)."""
        details    = signal.details
        symbol     = signal.symbol
        p_upbit    = details['p_upbit']
        p_bithumb  = details['p_bithumb']
        spread     = details['spread_pct']   # 이미 % 단위 (e.g., 0.709)

        # ① 쿨다운 체크
        if self._check_cooldown(symbol):
            remaining = COOLDOWN_SEC - (time.time() - self._cooldown.get(symbol, 0))
            print(f"  [{symbol}] 쿨다운 중 ({remaining:.0f}s 후 재가능)")
            return None

        # ② 방향 결정
        if p_upbit > p_bithumb:
            buy_exchange  = "bithumb"
            sell_exchange = "upbit"
            dir_str = "빗썸매수->업비트매도"
            side_balance = self.portfolio.bithumb_krw
        else:
            buy_exchange  = "upbit"
            sell_exchange = "bithumb"
            dir_str = "업비트매수->빗썸매도"
            side_balance = self.portfolio.upbit_krw

        # ③ Kelly or 고정 포지션 사이징
        ev_ratio = details.get('ev_pct', 0)
        if self.use_kelly:
            trade_size = self._kelly_position_size(ev_ratio, spread)
        else:
            trade_size = self._fixed_trade_krw

        # ④ 잔고 확인 + 자동 재배분
        if side_balance < trade_size:
            ok = self._auto_rebalance(trade_size)
            if not ok:
                return None
            side_balance = (
                self.portfolio.bithumb_krw if buy_exchange == "bithumb"
                else self.portfolio.upbit_krw
            )
        if side_balance < trade_size:
            return None

        # ⑤ API 오류 시뮬
        success, retried = self._simulate_api_error()
        if retried:
            self.portfolio.api_retry_count += 1
        if not success:
            print(f"  [{symbol}] API 오류 - 주문 실패 (재시도 후에도 실패)")
            return None

        # ⑥ 체결 지연 + 실체결가 조회 및 가용 볼륨 확인
        p_buy_fill, p_sell_fill, slip_pct, delay_ms, top_vol = await self._execute_with_delay(
            symbol, buy_exchange, p_upbit, p_bithumb
        )

        # 📌 팻테일 방어 수단: 호가 잔량 검증 (동적 포지션 축소)
        # 최우선 호가 잔량의 30%까지만 흡수하도록 투자금을 제한
        safe_volume = top_vol * 0.30
        if trade_size > safe_volume:
            print(f"  [{symbol}] 호가 얇음 방어: 타겟 {trade_size:,.0f}원 -> "
                  f"안전 한도 {safe_volume:,.0f}원으로 축소 (가용 볼륨: {top_vol:,.0f}원)")
            trade_size = safe_volume
            
        if trade_size < KELLY_MIN_KRW:
            print(f"  [{symbol}] 호가 부족으로 스킵 (투자금 {trade_size:,.0f}원 < 최소 {KELLY_MIN_KRW}원)")
            return None

        # ⑦ 잔고 재확인
        if side_balance < trade_size:
            return None

        # ⑧ 수익 계산
        qty          = trade_size / p_buy_fill
        gross_profit = qty * (p_sell_fill - p_buy_fill)
        total_fee    = trade_size * (TOTAL_BASE_FEE + slip_pct)
        net_profit   = gross_profit - total_fee
        ev_pct       = net_profit / trade_size * 100

        # ⑨ 포트폴리오 업데이트
        if buy_exchange == "bithumb":
            self.portfolio.bithumb_krw -= trade_size
            self.portfolio.upbit_krw   += trade_size + net_profit
        else:
            self.portfolio.upbit_krw   -= trade_size
            self.portfolio.bithumb_krw += trade_size + net_profit

        # ⑨ 쿨다운 등록 + 피크 업데이트
        self._update_cooldown(symbol)
        self.portfolio.update_peak()

        trade = PaperTrade(
            ts=time.time(),
            symbol=symbol,
            direction=dir_str,
            p_upbit_signal=p_upbit,
            p_bithumb_signal=p_bithumb,
            p_buy_fill=p_buy_fill,
            p_sell_fill=p_sell_fill,
            spread_pct=spread,
            actual_slippage_pct=slip_pct,
            trade_krw=trade_size,
            gross_profit=gross_profit,
            fee=total_fee,
            net_profit=net_profit,
            ev_pct=ev_pct,
            exec_delay_ms=delay_ms,
            api_retry=retried,
        )
        self.portfolio.trades.append(trade)
        return trade

    # ── 출력 ──────────────────────────────────────────────────────

    def _print_trade(self, trade: PaperTrade) -> None:
        ts   = datetime.fromtimestamp(trade.ts).strftime('%H:%M:%S')
        sign = "+" if trade.net_profit >= 0 else ""
        retry_tag  = "[재시도]" if trade.api_retry else ""
        slip_str   = f"슬리피지 {trade.actual_slippage_pct:.3%}"
        delay_str  = f"지연 {trade.exec_delay_ms}ms"
        print(
            f"  [{ts}]{retry_tag} {trade.symbol} {trade.direction} | "
            f"스프레드 {trade.spread_pct:.3f}% | {slip_str} | {delay_str} | "
            f"EV {sign}{trade.ev_pct:.3f}% | 순수익 {sign}{trade.net_profit:,.0f}원 | "
            f"투자 {trade.trade_krw:,.0f}원"
        )

    def _print_summary(self) -> None:
        p = self.portfolio
        elapsed_min = (time.time() - self._start_time) / 60
        net = p.total_profit - p.rebalance_cost_total
        print()
        print("=" * 70)
        print(f"  [페이퍼 시뮬 요약] 경과 {elapsed_min:.1f}분 / {self._scan_count}회 스캔")
        print(f"  업비트 KRW : {p.upbit_krw:>14,.0f}원")
        print(f"  빗썸   KRW : {p.bithumb_krw:>14,.0f}원")
        print(f"  총 자본    : {p.total_krw:>14,.0f}원")
        print(f"  누적 수익  : {p.total_profit:>+14,.0f}원")
        print(f"  수익률     : {p.total_return_pct:>+13.3f}%")
        print(f"  드로다운   : {p.drawdown_pct:>13.3f}%")
        print(f"  총 거래    : {len(p.trades):>14}건")
        print(f"  승률       : {p.win_rate * 100:>13.1f}%")
        if p.trades:
            print(f"  건당 평균  : {p.avg_profit_per_trade:>+14,.0f}원")
            print(f"  평균 슬리피지: {p.avg_slippage_pct:>11.4%}")
        print(f"  재배분 횟수: {p.rebalance_count:>14}회")
        print(f"  재배분 비용: {p.rebalance_cost_total:>+14,.0f}원")
        print(f"  API 실패   : {p.api_fail_count:>14}회")
        print(f"  API 재시도 : {p.api_retry_count:>14}회")
        print(f"  최종 순수익: {net:>+14,.0f}원")
        print("=" * 70)
        print()

    # ── 메인 루프 ────────────────────────────────────────────────

    async def run(self, max_scans: int | None = None) -> None:
        """페이퍼 트레이딩 루프."""
        p = self.portfolio
        kelly_str = "Kelly" if self.use_kelly else f"고정 {self._fixed_trade_krw:,.0f}원"
        print()
        print("=" * 70)
        print("  KRW 크로스 차익 - 페이퍼 트레이딩 시뮬레이터 v2")
        print("=" * 70)
        print(f"  초기 자본  : 업비트 {p.upbit_krw:,.0f}원 + 빗썸 {p.bithumb_krw:,.0f}원")
        print(f"  포지션     : {kelly_str}")
        print(f"  스캔 주기  : {self.scan_interval}초")
        print(f"  임계 스프레드: {KRW_CROSS_THRESHOLD:.2%}")
        print(f"  수수료     : {TOTAL_BASE_FEE:.2%} + 동적 슬리피지")
        print(f"  쿨다운     : {COOLDOWN_SEC}초")
        print(f"  API 실패율 : {API_FAIL_PROB:.0%}")
        print(f"  드로다운 정지: {MAX_DRAWDOWN_STOP:.0%}")
        print("  종료: Ctrl+C")
        print("=" * 70)
        print()

        while True:
            # 드로다운 정지
            if self.portfolio.drawdown_pct >= MAX_DRAWDOWN_STOP * 100:
                print(f"\n  [자동 정지] 드로다운 {self.portfolio.drawdown_pct:.1f}% 도달!")
                self._stopped = True
                break

            self._scan_count += 1
            now = datetime.now().strftime('%H:%M:%S')
            print(f"[{now}] 스캔 #{self._scan_count}")

            try:
                signals = await self.scanner.scan_once()
            except Exception as e:
                logger.error(f"스캔 오류: {e}")
                signals = []

            if signals:
                # EV 높은 순으로 정렬 (멀티코인 우선순위)
                signals.sort(
                    key=lambda s: s.details.get('ev_pct', 0),
                    reverse=True,
                )
                for signal in signals:
                    trade = await self._execute_paper_trade(signal)
                    if trade:
                        self._print_trade(trade)
            else:
                print("  (신호 없음 - 스프레드 임계점 미달)")

            if self._scan_count % 10 == 0:
                self._print_summary()

            if max_scans and self._scan_count >= max_scans:
                break

            await asyncio.sleep(self.scan_interval)

        self._print_summary()


# ─────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KRW 크로스 차익 페이퍼 트레이딩 v2")
    parser.add_argument("--capital",    type=float, default=5_000_000,
                        help="각 거래소 초기 자본 (원, 기본: 5,000,000)")
    parser.add_argument("--trade-size", type=float, default=None,
                        help="고정 투자금 (원, 기본: capital의 20%%)")
    parser.add_argument("--interval",  type=float, default=30.0,
                        help="스캔 주기 (초)")
    parser.add_argument("--scans",     type=int,   default=None,
                        help="최대 스캔 횟수 (기본: 무한)")
    parser.add_argument("--use-kelly", action="store_true",
                        help="Kelly Criterion 포지션 사이징 사용")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    trader = PaperTrader(
        per_side_krw=args.capital,
        scan_interval=args.interval,
        use_kelly=args.use_kelly,
        fixed_trade_krw=args.trade_size,
    )

    try:
        asyncio.run(trader.run(max_scans=args.scans))
    except KeyboardInterrupt:
        print()
        print("[종료] 시뮬레이션 중단")
        trader._print_summary()
