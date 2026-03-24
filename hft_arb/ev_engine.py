"""
ev_engine.py — In-memory 기대값(EV) 계산 엔진
===============================================
[설계 원칙]
  - DB I/O 완전 배제 (순수 In-memory 계산)
  - 분모 0 방어, NaN/Inf 전파 방지
  - 코인별 독립 임계점 적용 (BTC/ETH/SOL)
  - 실시간 환율 피드 연동 (fx_feed.py)

[QuantAnalyst] 검증된 EV 공식:
  A. 펀딩비 차익: EV = FR * N - C_total
  B. 김치 프리미엄: EV = (P_krw/FX - P_usd) * Q - C_total
  C. Polymarket 괴리: EV = (1.0 - S) * N - C_total
"""

import logging
import math
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────
# 진입 임계점 (코인별 독립 설정)
# ──────────────────────────────────────────
FUNDING_RATE_THRESHOLD = 0.0020       # 0.20% / 8h

# 코인별 김치 프리미엄 임계점
# ETH/SOL은 유동성이 낮아 슬리피지 보정을 위해 높게 설정
KIMCHI_THRESHOLDS: dict[str, float] = {
    "BTC": 0.0070,    # 0.70% — 최고 유동성
    "ETH": 0.0090,    # 0.90% — 중간 유동성
    "SOL": 0.0120,    # 1.20% — 낮은 유동성
}

POLYMARKET_GAP_THRESHOLD = 0.0300     # 3.00% (S <= 0.97)

# ──────────────────────────────────────────
# 수수료 파라미터 (보수적 추정)
# ──────────────────────────────────────────
FEE_BINANCE_MAKER_FUTURE = 0.0002    # 0.02%
FEE_BINANCE_TAKER_SPOT   = 0.0010    # 0.10%
FEE_NETWORK_USDT_FIXED   = 1.0       # $1.0 (ERC-20 보수적 추정)
FEE_SLIPPAGE_FUTURE      = 0.0005    # 0.05%
FEE_UPBIT_TAKER          = 0.0005    # 0.05%
FEE_BITHUMB_TAKER        = 0.0025    # 0.25% ← 빗썸 기본 수수료
FEE_FX_SPREAD            = 0.0020    # 0.20%
FEE_SLIPPAGE_SPOT        = 0.0010    # 0.10%
FEE_BTC_NETWORK_USD      = 5.0       # $5 (코인 전송 보수적 추정)
FEE_POLY_TAKER           = 0.0020    # 0.20% per side
FEE_SLIPPAGE_POLY        = 0.0050    # 0.50% per side (유동성 얇음)

# KRW 크로스 차익 총 수수료 (업비트 + 빗썸 + 슬리피지)
# 전송비: $0 (코인 이동 없음, 양쪽에 코인 예치)
KRW_CROSS_TOTAL_FEE = FEE_UPBIT_TAKER + FEE_BITHUMB_TAKER + FEE_SLIPPAGE_SPOT * 2
# 0.05% + 0.25% + 0.10% × 2 = 0.50% → 이 이상 스프레드면 수익

# KRW 크로스 차익 손익분기 스프레드
KRW_CROSS_THRESHOLD = 0.0060    # 0.60% (안전 마진 0.10% 포함)


@dataclass
class ArbitrageSignal:
    """차익거래 신호 데이터 클래스."""
    strategy: str           # "funding_arb" | "kimchi_arb" | "polymarket_arb"
    symbol: str
    ev_usd: float           # 기대 수익 (USD)
    ev_pct: float           # 기대 수익률 (%)
    position_size: float    # 포지션 금액 (USD)
    details: dict = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def is_valid(self) -> bool:
        """EV > 0 AND 임계점 초과 여부."""
        return self.ev_usd > 0 and not math.isnan(self.ev_pct) and not math.isinf(self.ev_pct)


class EVEngine:
    """
    In-memory 기대값 계산 엔진.

    WebSocket 피드에서 데이터를 수신할 때마다 EV를 즉시 계산한다.
    EV > 임계점인 경우 ArbitrageSignal을 반환한다.

    Args:
        position_size_usd: 기본 포지션 크기 (USD)
        fx_rate_krw: USD/KRW 초기 환율 (fx_feed.py가 실시간 갱신)
    """

    def __init__(self, position_size_usd: float = 10000.0, fx_rate_krw: float = 1445.0):
        self.position_size_usd = position_size_usd
        self.fx_rate_krw = fx_rate_krw

        # In-memory 최신 데이터 캐시
        self._funding_cache: dict[str, dict] = {}
        self._binance_spot_cache: dict[str, dict] = {}
        self._upbit_cache: dict[str, dict] = {}
        self._poly_cache: dict[str, dict] = {}        # condition_id -> {p_yes, p_no}
        self._external_cache: dict[str, dict] = {}    # platform_id -> {prices, title}

        from hft_arb.mapper import EventMapper
        self.mapper = EventMapper()

    async def on_data_callback(self, data: dict) -> None:
        """모든 WS/GraphQL 피드 통합 콜백."""
        dtype = data.get("type")

        if dtype == "polymarket_gap":
            self._poly_cache[data["condition_id"]] = {
                "p_yes": data["p_yes"],
                "p_no": data["p_no"],
                "token_ids": data["token_ids"]
            }
            sig = self.calc_polymarket_arb(
                data["condition_id"], data["p_yes"], data["p_no"], data["token_ids"]
            )
            ext_id = self.mapper.get_cross_platform_id(data["condition_id"])
            if ext_id and ext_id in self._external_cache:
                pass  # 크로스 플랫폼 EV 계산 로직 (향후 추가)

        elif dtype == "external_price":
            self._external_cache[data["external_id"]] = {
                "prices": data["prices"],
                "title": data["title"],
                "platform": data["platform"]
            }

    # ──────────────────────────────────────────
    # A. 펀딩비 차익 EV 계산
    # ──────────────────────────────────────────
    def calc_funding_arb(self, funding_rate: float, symbol: str) -> ArbitrageSignal | None:
        """
        펀딩비 차익 EV 계산.

        EV = FR * N - (C_maker_future + C_taker_spot + C_network + C_slippage)

        Args:
            funding_rate: 8시간 펀딩비율 (예: 0.002 = 0.20%)
            symbol: 거래쌍 (예: "BTCUSDT")

        Returns:
            ArbitrageSignal 또는 None (임계점 미달 시)
        """
        N = self.position_size_usd

        # [SecurityAuditor HIGH] 분모 0 방어
        if N <= 0:
            return None

        if funding_rate < FUNDING_RATE_THRESHOLD:
            return None

        gross = funding_rate * N
        c_total = (
            N * FEE_BINANCE_MAKER_FUTURE
            + N * FEE_BINANCE_TAKER_SPOT
            + FEE_NETWORK_USDT_FIXED
            + N * FEE_SLIPPAGE_FUTURE
        )
        ev = gross - c_total
        ev_pct = (ev / N) * 100

        logger.info(
            f"[EV:Funding] {symbol} FR={funding_rate:.4%} | "
            f"EV=${ev:.2f} ({ev_pct:.4f}%) | 임계={FUNDING_RATE_THRESHOLD:.4%}"
        )

        return ArbitrageSignal(
            strategy="funding_arb",
            symbol=symbol,
            ev_usd=ev,
            ev_pct=ev_pct,
            position_size=N,
            details={
                "funding_rate": funding_rate,
                "gross_usd": gross,
                "cost_usd": c_total,
                "threshold_pct": FUNDING_RATE_THRESHOLD * 100,
            },
        )

    # ──────────────────────────────────────────
    # B. 김치 프리미엄 차익 EV 계산 (멀티코인)
    # ──────────────────────────────────────────
    def calc_kimchi_arb(
        self,
        p_krw: float,
        p_usd: float,
        symbol: str = "BTC",
        quantity: float = 0.01,
    ) -> ArbitrageSignal | None:
        """
        김치 프리미엄 차익 EV 계산 (BTC/ETH/SOL 멀티코인 지원).

        KP = (P_krw / FX - P_usd) / P_usd
        EV = (P_krw / FX - P_usd) * Q - C_total

        Args:
            p_krw: Upbit 원화 가격 (BTC/ETH/SOL)
            p_usd: Binance USDT 가격
            symbol: 코인 심볼 ("BTC", "ETH", "SOL")
            quantity: 거래 수량

        Returns:
            ArbitrageSignal 또는 None
        """
        fx = self.fx_rate_krw

        # [SecurityAuditor HIGH] 분모 0 방어
        if p_usd <= 0 or fx <= 0:
            logger.warning(f"[EV:Kimchi:{symbol}] p_usd 또는 fx_rate가 0 이하. 계산 스킵.")
            return None

        p_krw_in_usd = p_krw / fx
        kp = (p_krw_in_usd - p_usd) / p_usd

        # 코인별 독립 임계점 적용
        threshold = KIMCHI_THRESHOLDS.get(symbol, 0.0090)
        if kp < threshold:
            return None

        gross_usd = (p_krw_in_usd - p_usd) * quantity
        N = p_usd * quantity

        # [SecurityAuditor MEDIUM] N=0 방어
        if N <= 0:
            return None

        c_total = (
            N * FEE_UPBIT_TAKER
            + N * FEE_BINANCE_TAKER_SPOT
            + N * FEE_SLIPPAGE_SPOT
            + N * FEE_FX_SPREAD
            + FEE_BTC_NETWORK_USD
        )
        ev = gross_usd - c_total
        ev_pct = (ev / N) * 100

        logger.info(
            f"[EV:Kimchi:{symbol}] KP={kp:.4%} threshold={threshold:.4%} | "
            f"EV=${ev:.2f} ({ev_pct:.4f}%) FX={fx:.1f}"
        )

        return ArbitrageSignal(
            strategy="kimchi_arb",
            symbol=symbol,
            ev_usd=ev,
            ev_pct=ev_pct,
            position_size=N,
            details={
                "kimchi_premium_pct": kp * 100,
                "threshold_pct": threshold * 100,
                "p_usd": p_usd,
                "p_krw": p_krw,
                "fx_rate": fx,
                "gross_usd": gross_usd,
                "cost_usd": c_total,
            },
        )

    # ──────────────────────────────────────────
    # C. Polymarket 확률 괴리 차익 EV 계산
    # ──────────────────────────────────────────
    def calc_polymarket_arb(
        self,
        condition_id: str,
        p_yes: float,
        p_no: float,
        token_ids: dict | None = None,
    ) -> ArbitrageSignal | None:
        """
        Polymarket 확률 괴리 차익 EV 계산.

        S = P_yes + P_no  (정상 = 1.0)
        gap = 1.0 - S
        EV = gap * N - C_total

        Args:
            condition_id: Polymarket 시장 ID
            p_yes: Yes 토큰 가격 (0~1)
            p_no: No 토큰 가격 (0~1)
            token_ids: Yes/No 토큰 ID 딕셔너리 (선택)

        Returns:
            ArbitrageSignal 또는 None
        """
        total = p_yes + p_no
        gap = 1.0 - total

        if gap < POLYMARKET_GAP_THRESHOLD:
            return None

        N = self.position_size_usd
        gross = gap * N
        c_total = N * 2 * (FEE_POLY_TAKER + FEE_SLIPPAGE_POLY)
        ev = gross - c_total
        ev_pct = (ev / N) * 100 if N > 0 else 0.0

        # [SecurityAuditor HIGH] NaN/Inf 방어
        if math.isnan(ev) or math.isinf(ev):
            return None

        logger.info(
            f"[EV:Polymarket] {condition_id[:16]}... "
            f"S={total:.4f} gap={gap:.4%} EV=${ev:.2f} ({ev_pct:.4f}%)"
        )

        return ArbitrageSignal(
            strategy="polymarket_arb",
            symbol=condition_id,
            ev_usd=ev,
            ev_pct=ev_pct,
            position_size=N,
            details={
                "p_yes": p_yes,
                "p_no": p_no,
                "total": total,
                "gap_pct": gap * 100,
                "gross_usd": gross,
                "cost_usd": c_total,
                "token_ids": token_ids,
            },
        )

    def update_fx_rate(self, fx_rate_krw: float) -> None:
        """환율 실시간 업데이트 (fx_feed.py에서 호출)."""
        if fx_rate_krw > 0:
            self.fx_rate_krw = fx_rate_krw

    # ──────────────────────────────────────────
    # D. 업비트↔빗썸 KRW 크로스 차익 EV 계산
    # ──────────────────────────────────────────
    def calc_krw_cross_arb(
        self,
        p_upbit: float,
        p_bithumb: float,
        symbol: str = "BTC",
        quantity: float = 0.01,
    ) -> ArbitrageSignal | None:
        """
        업비트↔빗썸 KRW 크로스 차익 EV 계산.

        코인 전송 불필요 (양쪽에 코인/KRW 예치 후 동시 주문):
          - 빗썸 > 업비트: 업비트 매수 + 빗썸 매도 (동시)
          - 업비트 > 빗썸: 빗썸 매수 + 업비트 매도 (동시)

        EV = (P_high - P_low) * Q - C_total
        C_total = P_avg * Q * (upbit_fee + bithumb_fee + slippage*2)
               = P_avg * Q * 0.50%  (전송비 $0)

        Args:
            p_upbit: 업비트 현재가 (원)
            p_bithumb: 빗썸 현재가 (원)
            symbol: 코인 심볼
            quantity: 거래 수량

        Returns:
            ArbitrageSignal 또는 None
        """
        # [SecurityAuditor HIGH] 분모 0 방어
        if p_upbit <= 0 or p_bithumb <= 0:
            logger.warning(f"[EV:KRW_Cross:{symbol}] 가격이 0 이하. 스킵.")
            return None

        p_high = max(p_upbit, p_bithumb)
        p_low  = min(p_upbit, p_bithumb)
        p_avg  = (p_high + p_low) / 2

        spread_pct = (p_high - p_low) / p_low

        if spread_pct < KRW_CROSS_THRESHOLD:
            return None  # 임계점 미달

        gross_krw = (p_high - p_low) * quantity
        N_krw = p_avg * quantity

        # 양쪽 수수료 + 슬리피지 (전송비 없음!)
        c_total_krw = N_krw * KRW_CROSS_TOTAL_FEE  # 0.50%

        ev_krw = gross_krw - c_total_krw
        ev_usd = ev_krw / self.fx_rate_krw  # 참고용 USD 환산

        ev_pct = (ev_krw / N_krw) * 100

        # [SecurityAuditor HIGH] NaN/Inf 방어
        if math.isnan(ev_usd) or math.isinf(ev_usd):
            return None

        # 방향 결정
        if p_bithumb > p_upbit:
            direction = "업비트매수→빗썸매도"
        else:
            direction = "빗썸매수→업비트매도"

        logger.info(
            f"[EV:KRW_Cross:{symbol}] spread={spread_pct:.4%} "
            f"임계={KRW_CROSS_THRESHOLD:.4%} | "
            f"EV={ev_krw:,.0f}원 ({ev_pct:.4f}%) | {direction}"
        )

        return ArbitrageSignal(
            strategy="krw_cross_arb",
            symbol=symbol,
            ev_usd=ev_usd,
            ev_pct=ev_pct,
            position_size=N_krw / self.fx_rate_krw,
            details={
                "p_upbit": p_upbit,
                "p_bithumb": p_bithumb,
                "spread_pct": spread_pct * 100,
                "threshold_pct": KRW_CROSS_THRESHOLD * 100,
                "gross_krw": gross_krw,
                "cost_krw": c_total_krw,
                "ev_krw": ev_krw,
                "direction": direction,
                "network_fee": 0,  # 전송비 없음!
            },
        )


if __name__ == "__main__":
    engine = EVEngine(position_size_usd=10000.0)
    sig = engine.calc_funding_arb(funding_rate=0.0025, symbol="BTCUSDT")
    print(f"Funding signal: {sig}")
    sig2 = engine.calc_polymarket_arb("test_id", p_yes=0.45, p_no=0.50)
    print(f"Polymarket signal: {sig2}")
    # 멀티코인 김치 테스트
    sig3 = engine.calc_kimchi_arb(p_krw=107_000_000, p_usd=78_000, symbol="BTC", quantity=0.01)
    print(f"Kimchi BTC signal: {sig3}")
