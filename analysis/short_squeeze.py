"""
숏스퀴즈 포착 엔진 (Short Squeeze Detection Engine)
====================================================

전략 배경:
  - 공매도 잔고가 누적된 종목에서 주가 상승 시 숏커버링 강제 발생
  - 특히 유동주식수(float)가 적은 종목에서 연쇄 커버링으로 급등 발생
  - 옵션 콜 OI 급증 시 마켓메이커 델타 헤지 → 감마스퀴즈 병행 가능 (GME 사례)

핵심 지표 및 수식:
  1. short_float_pct   = sharesShort / floatShares
  2. days_to_cover     = sharesShort / avgVolume  (커버 완료 예상 일수)
  3. volume_surge      = todayVolume / avg20Volume (거래량 상승 배수)
  4. momentum_5d       = (close[-1] - close[-5]) / close[-5]
  5. rsi_zone          = RSI 14일 (30~50 구간이 위험 — 숏 입장에서 반등 임박)
  6. float_size_inv    = 유동주식수 역수 (작을수록 스퀴즈 강도 증가)
  7. gamma_exposure    = (근거리 콜 OI × 100) / floatShares (감마스퀴즈 위험)

Squeeze Score 수식:
  score = Σ(weight_i × normalized_component_i) × 100
  가중치: short_float=0.28, days_to_cover=0.22, volume=0.20, momentum=0.15, rsi=0.10, float=0.05

진입 기준:
  ≥ 75: STRONG_SQUEEZE  (즉시 모니터링 / 진입 검토)
  ≥ 55: WATCH           (관심 목록 유지)
  ≥ 40: DEVELOPING      (미성숙 — 계속 모니터링)
   < 40: NO_SIGNAL

데이터 소스:
  - 미국 주식: Yahoo Finance (yfinance) — info + OHLCV + options
  - 한국 주식: 공매도 데이터 없음 (KRX/DART는 별도 API 필요) → 기술적 지표만 제공
"""

import time
import numpy as np
import pandas as pd
import yfinance as yf
from typing import Optional
from datetime import datetime, timedelta


# ================================================================
# 상수 — 가중치, 임계값, 레벨 정의
# ================================================================

WEIGHTS = {
    "short_float_pct": 0.28,   # 공매도 점유율 (가장 중요)
    "days_to_cover":   0.22,   # 커버 일수
    "volume_surge":    0.20,   # 거래량 급등
    "momentum_5d":     0.15,   # 5일 모멘텀
    "rsi_zone":        0.10,   # RSI 위험 구간 (30~50)
    "float_size_inv":  0.05,   # 유동주식수 역수
}

THRESHOLDS = {
    "short_float_extreme": 0.35,   # 35% 이상 → 극단적 공매도
    "short_float_high":    0.20,   # 20% 이상 → 높은 공매도
    "days_to_cover_cap":  20.0,    # 이상치 상한 (유동성 위험 별도 경고)
    "days_to_cover_high":  5.0,    # 5일 이상 → 높음
    "volume_surge_cap":    5.0,    # 거래량 이상치 상한
    "volume_surge_high":   2.0,    # 2배 이상 → 유의미한 급등
    "float_micro":        10e6,    # 1천만주 이하 → 극소형 플로트
    "float_small":        50e6,    # 5천만주 이하 → 소형 플로트
    "gamma_extreme":      20.0,    # 20% 이상 → 극단적 감마 노출 (%)
    "gamma_high":         10.0,    # 10% 이상 → 높은 감마 노출
}

# 레벨 정의: {최소점수: (레벨명, 요약, 자동매매 신호)}
SQUEEZE_LEVELS = {
    75: ("STRONG_SQUEEZE", "🚨 강력한 숏스퀴즈 신호 — 즉시 모니터링", "ENTER"),
    55: ("WATCH",          "👀 스퀴즈 형성 중 — 관심 목록 유지",     "PARTIAL"),
    40: ("DEVELOPING",     "🔄 초기 신호 — 아직 미성숙",              "HOLD"),
     0: ("NO_SIGNAL",      "➖ 유의미한 신호 없음",                    "HOLD"),
}


class ShortSqueezeAnalyzer:
    """
    숏스퀴즈 포착 및 스코어링 엔진

    기능:
      - 단일 종목 전체 분석 (analyze)
      - 워치리스트 스크리닝 + 랭킹 (screen)
      - 공매도 잔고 추이(전월 대비) 분석 (get_historical_short_interest)
      - 옵션 감마 익스포저 계산 (감마스퀴즈 위험 수치화)

    Usage:
        sq = ShortSqueezeAnalyzer()

        # 단일 종목
        result = sq.analyze("GME")

        # 워치리스트 스크리닝
        top = sq.screen(["GME", "AMC", "NVDA", "AAPL", "005930.KS"], top_n=5)
        for r in top:
            print(r["ticker"], r["squeeze_score"], r["level"])
    """

    def __init__(self, rate_delay: float = 0.6):
        """
        Args:
            rate_delay: Yahoo Finance API 호출 간 딜레이(초) — 과부하 방지
        """
        self.rate_delay = rate_delay

    # ────────────────────────────────────────────────────────────
    # 내부 — 데이터 수집
    # ────────────────────────────────────────────────────────────

    def _get_info(self, ticker: str) -> Optional[dict]:
        """Yahoo Finance 기업 정보 수집 (공매도, 유동주식수, 평균거래량 등)"""
        try:
            info = yf.Ticker(ticker).info
            time.sleep(self.rate_delay)
            return info
        except Exception as e:
            print(f"❌ [{ticker}] info 수집 실패: {e}")
            return None

    def _get_ohlcv(self, ticker: str, period: str = "3mo") -> pd.DataFrame:
        """3개월 OHLCV 수집 — 기술적 지표 계산용"""
        try:
            df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            time.sleep(self.rate_delay)
            return df
        except Exception as e:
            print(f"❌ [{ticker}] OHLCV 수집 실패: {e}")
            return pd.DataFrame()

    def _get_option_gamma_exposure(self, ticker: str, float_shares: int) -> dict:
        """
        감마 익스포저 근사치 계산 (감마스퀴즈 위험 정량화)

        원리:
          - 투자자들이 콜옵션을 대거 매수하면, 마켓메이커는 델타 헤지를 위해 주식 매수
          - 주가 상승 → 델타 증가 → 추가 매수 → 양의 피드백 루프 = 감마스퀴즈
          - 공식: gamma_exposure % = (근거리 만기 콜 OI × 100주/계약) / float_shares × 100

        Returns:
            dict: gamma_exposure_pct, call_oi_near, put_oi_near, near_pcr, gamma_signal
        """
        result = {
            "gamma_exposure_pct": 0.0,
            "call_oi_near":       0,
            "put_oi_near":        0,
            "near_pcr":           None,
            "gamma_signal":       "옵션 데이터 없음",
        }

        try:
            t = yf.Ticker(ticker)
            expirations = t.options
            if not expirations:
                return result

            # 30일 이내 만기 옵션만 사용 (감마 영향이 가장 큰 near-term)
            cutoff = datetime.now() + timedelta(days=30)
            near_expiries = [
                e for e in expirations
                if datetime.strptime(e, "%Y-%m-%d") <= cutoff
            ][:3]  # 최대 3개 만기일 집계

            call_oi_total = 0
            put_oi_total  = 0
            for exp in near_expiries:
                try:
                    chain = t.option_chain(exp)
                    call_oi_total += int(chain.calls["openInterest"].fillna(0).sum())
                    put_oi_total  += int(chain.puts["openInterest"].fillna(0).sum())
                except Exception:
                    continue

            result["call_oi_near"] = call_oi_total
            result["put_oi_near"]  = put_oi_total
            if call_oi_total > 0:
                result["near_pcr"] = round(put_oi_total / call_oi_total, 3)

            # 감마 익스포저 비율 계산
            if float_shares and float_shares > 0:
                gamma_exp_pct = (call_oi_total * 100) / float_shares * 100
                result["gamma_exposure_pct"] = round(gamma_exp_pct, 2)

            # 위험 레벨 분류
            gep = result["gamma_exposure_pct"]
            if gep >= THRESHOLDS["gamma_extreme"]:
                result["gamma_signal"] = "🚨 극단적 감마 노출 — 감마스퀴즈 위험"
            elif gep >= THRESHOLDS["gamma_high"]:
                result["gamma_signal"] = "⚠️ 높은 감마 노출 — 주시 필요"
            elif gep >= 5:
                result["gamma_signal"] = "📌 보통 감마 노출"
            else:
                result["gamma_signal"] = "✅ 낮은 감마 노출"

        except Exception as e:
            print(f"⚠️ [{ticker}] 감마 익스포저 계산 실패: {e}")

        return result

    # ────────────────────────────────────────────────────────────
    # 내부 — 지표 계산
    # ────────────────────────────────────────────────────────────

    def _calc_short_metrics(self, info: dict) -> dict:
        """
        공매도 핵심 지표 계산

        공식:
          short_pct_float = sharesShort / floatShares
          days_to_cover   = sharesShort / averageVolume  (Yahoo 직접 제공 or 직접 계산)
          borrow_rate_est = 공매도 비율 기반 차입비용 추정 (휴리스틱)
        """
        shares_short    = info.get("sharesShort", 0) or 0
        float_shares    = info.get("floatShares",  0) or 0
        avg_volume      = info.get("averageVolume", 0) or 0
        short_ratio     = info.get("shortRatio",    None)  # Yahoo 직접 제공 (days to cover)
        short_pct_float = info.get("shortPercentOfFloat", None)  # 정상: 0~1 범위

        # [SECURITY-MEDIUM] Yahoo Finance는 때때로 shortPercentOfFloat를
        # 소수(0.35) 대신 백분율(35.0)로 반환하는 케이스 있음.
        # 1.0 초과 시 100으로 나눠 소수 범위로 강제 정규화.
        if short_pct_float is not None and float(short_pct_float) > 1.0:
            short_pct_float = float(short_pct_float) / 100.0

        # Yahoo 직접 제공 필드 없을 때 직접 계산
        # [SECURITY-MEDIUM] avg_volume=0 방어: 나눗셈 전 명시적 0 체크
        if short_ratio is None:
            if avg_volume and avg_volume > 0:
                short_ratio = float(shares_short) / float(avg_volume)
            else:
                short_ratio = 0.0  # 거래량 없는 종목 → 0 처리 (급락주/상폐 직전 종목)
        if short_pct_float is None:
            if float_shares and float_shares > 0:
                short_pct_float = float(shares_short) / float(float_shares)
            else:
                short_pct_float = 0.0

        # NaN/Inf 전파 방어
        short_ratio     = float(short_ratio)     if short_ratio     is not None else 0.0
        short_pct_float = float(short_pct_float) if short_pct_float is not None else 0.0
        if not (0.0 <= short_ratio     < 1e9):  short_ratio     = 0.0  # noqa
        if not (0.0 <= short_pct_float <= 1.0): short_pct_float = 0.0  # noqa

        # 이상치 상한 처리
        days_to_cover = min(short_ratio, THRESHOLDS["days_to_cover_cap"])
        spf = short_pct_float

        # 차입비용(Borrow Rate) 추정 — 업계 경험치 기반 휴리스틱
        # 정밀 값은 IB, Ortex, S3 Partners 등 유료 서비스 필요
        if spf >= 0.35:
            borrow_rate_est = "∞ (Hard-to-Borrow / 사실상 불가)"
        elif spf >= 0.20:
            borrow_rate_est = f"~{spf * 200:.0f}%+ p.a. (매우 높음)"
        elif spf >= 0.10:
            borrow_rate_est = f"~{spf * 80:.0f}%+ p.a. (높음)"
        elif spf >= 0.05:
            borrow_rate_est = f"~{spf * 30:.0f}%+ p.a. (보통)"
        else:
            borrow_rate_est = "~1~3% p.a. (낮음 — Easy-to-Borrow)"

        return {
            "shares_short":    int(shares_short),
            "float_shares":    int(float_shares),
            "short_pct_float": round(spf, 4),     # 예: 0.35 = 35%
            "days_to_cover":   round(days_to_cover, 2),
            "borrow_rate_est": borrow_rate_est,
        }

    def _calc_technical_metrics(self, ohlcv: pd.DataFrame) -> dict:
        """
        기술적 지표 계산

        포함 지표:
          - 거래량 Surge Ratio (오늘/20일 평균)
          - 모멘텀 1d, 5d, 10d, 20d
          - RSI 14일 (Wilder's smoothing)
          - 볼린저밴드 %B
          - 52주 내 현재 위치 (저점 대비 반등률)
        """
        if ohlcv.empty or len(ohlcv) < 20:
            return {}

        close  = ohlcv["Close"]
        volume = ohlcv["Volume"]

        # 거래량 Surge Ratio
        vol_20ma  = volume.rolling(20).mean()
        vol_ratio = float(volume.iloc[-1] / vol_20ma.iloc[-1]) if float(vol_20ma.iloc[-1]) > 0 else 1.0
        vol_ratio = min(vol_ratio, THRESHOLDS["volume_surge_cap"])

        # 모멘텀 — N일 수익률
        def safe_mom(days: int) -> float:
            if len(close) <= days:
                return 0.0
            base = float(close.iloc[-days - 1])
            return float((close.iloc[-1] - base) / base) if base != 0 else 0.0

        # RSI 14 (Wilder's Smoothing)
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rs    = gain / loss.replace(0, np.nan)
        rsi_val = float(100 - 100 / (1 + rs.iloc[-1])) if not np.isnan(float(rs.iloc[-1])) else 50.0

        # 볼린저밴드 %B
        ma20  = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper = ma20 + 2 * std20
        lower = ma20 - 2 * std20
        band_width = float(upper.iloc[-1] - lower.iloc[-1])
        pct_b = float((close.iloc[-1] - lower.iloc[-1]) / band_width) if band_width > 0 else 0.5

        # 52주 내 현재 위치 (저점~고점 사이 비율)
        high_52w = float(close.rolling(min(252, len(close))).max().iloc[-1])
        low_52w  = float(close.rolling(min(252, len(close))).min().iloc[-1])
        range_52w = high_52w - low_52w
        pos_52w  = float((close.iloc[-1] - low_52w) / range_52w) if range_52w > 0 else 0.5

        return {
            "current_price":  round(float(close.iloc[-1]), 4),
            "volume_ratio":   round(vol_ratio, 3),
            "mom_1d":         round(safe_mom(1),  4),
            "mom_5d":         round(safe_mom(5),  4),
            "mom_10d":        round(safe_mom(10), 4),
            "mom_20d":        round(safe_mom(20), 4),
            "rsi_14":         round(rsi_val, 2),
            "bb_pct_b":       round(pct_b, 4),
            "pos_in_52w_range": round(pos_52w, 4),
        }

    def _compute_squeeze_score(
        self,
        short_metrics: dict,
        tech_metrics:  dict,
        float_shares:  int,
    ) -> dict:
        """
        Squeeze Score 계산 (0~100점)

        각 컴포넌트를 [0, 1]로 정규화 후 가중합 × 100

        정규화 방법:
          - short_float_pct: [0, extreme(0.35)] → [0, 1] 선형
          - days_to_cover:   [0, cap(20)] → [0, 1] 선형
          - volume_surge:    [(1배 초과분)을 cap에 선형 정규화]
          - momentum_5d:     sigmoid (−∞~+∞ → 0~1, 5%상승 ≈ 0.75)
          - rsi_zone:        RSI 30 → 1.0, RSI 50 → 0.0, RSI < 30 → 1.0, RSI > 50 → 0.0
          - float_size_inv:  micro→1.0, small→0.6, large→선형 감소
        """
        components: dict[str, float] = {}

        # 1. 공매도 점유율
        spf = short_metrics.get("short_pct_float", 0)
        components["short_float_pct"] = min(spf / THRESHOLDS["short_float_extreme"], 1.0)

        # 2. 커버 일수
        dtc = short_metrics.get("days_to_cover", 0)
        components["days_to_cover"] = min(dtc / THRESHOLDS["days_to_cover_cap"], 1.0)

        # 3. 거래량 급등 (1배 기준 초과분만 점수화)
        vr  = max(0.0, tech_metrics.get("volume_ratio", 1.0) - 1.0)
        components["volume_surge"] = min(vr / (THRESHOLDS["volume_surge_cap"] - 1.0), 1.0)

        # 4. 5일 모멘텀 — 시그모이드 정규화
        m5d = tech_metrics.get("mom_5d", 0)
        # 5% 수익 ≈ 0.731, 10% ≈ 0.880, -5% ≈ 0.269
        components["momentum_5d"] = float(1 / (1 + np.exp(-20 * m5d)))

        # 5. RSI 위험 구간 (숏 입장에서 가장 위험한 구간 = 30~50, 반등 임박)
        rsi = tech_metrics.get("rsi_14", 50)
        if rsi < 30:
            components["rsi_zone"] = 1.0                      # 극단적 과매도 → 반등 최고 위험
        elif rsi <= 50:
            components["rsi_zone"] = 1.0 - (rsi - 30) / 20   # 30→1.0 선형 감소 → 50→0.0
        else:
            components["rsi_zone"] = 0.0                      # 이미 과매수 → 숏커버링 덜 위험

        # 6. 유동주식수 역수 (작을수록 스퀴즈 강도 증가)
        if float_shares and float_shares > 0:
            if float_shares <= THRESHOLDS["float_micro"]:
                components["float_size_inv"] = 1.0
            elif float_shares <= THRESHOLDS["float_small"]:
                # 1000만 → 100만: 1.0, 5000만 → 0.6
                components["float_size_inv"] = 0.6
            else:
                # 5천만 이상: 선형 감소 (5억주 이상 ≈ 0)
                val = 0.6 * (1 - (float_shares - THRESHOLDS["float_small"]) / 450e6)
                components["float_size_inv"] = max(0.0, val)
        else:
            components["float_size_inv"] = 0.0

        # 최종 가중합
        score = sum(WEIGHTS[k] * v for k, v in components.items() if k in WEIGHTS) * 100

        return {
            "squeeze_score": round(score, 1),
            "components":    {k: round(v, 4) for k, v in components.items()},
        }

    # ────────────────────────────────────────────────────────────
    # 공개 API
    # ────────────────────────────────────────────────────────────

    def analyze(self, ticker: str, include_options: bool = True) -> dict:
        """
        단일 종목 전체 숏스퀴즈 분석

        Args:
            ticker:          종목 코드 (미국: "GME", 한국: "005930.KS")
            include_options: 옵션 감마 익스포저 계산 여부 (시간 추가 소요)

        Returns:
            {
              ticker, timestamp, squeeze_score, level, signal, summary,
              short_metrics, technical, gamma, risk_note, components
            }
        """
        print(f"\n🔍 [{ticker}] 숏스퀴즈 분석 시작...")

        is_korean = ".KS" in ticker or ".KQ" in ticker
        if is_korean:
            print(f"  ⚠️ 한국 주식 — Yahoo Finance 공매도 데이터 없음. 기술적 지표만 사용.")

        result = {
            "ticker":        ticker,
            "timestamp":     datetime.now().isoformat(),
            "is_korean":     is_korean,
            "squeeze_score": 0.0,
            "level":         "NO_SIGNAL",
            "signal":        "HOLD",
            "summary":       "",
            "short_metrics": {},
            "technical":     {},
            "gamma":         {},
            "risk_note":     "",
            "components":    {},
        }

        # Step 1: 기업 정보 수집
        info = self._get_info(ticker)
        if not info:
            result["summary"] = "Yahoo Finance 데이터 수집 실패"
            return result

        # Step 2: OHLCV + 기술적 지표
        ohlcv = self._get_ohlcv(ticker)
        tech  = self._calc_technical_metrics(ohlcv)
        result["technical"] = tech

        # Step 3: 공매도 지표 (한국 주식은 더미값)
        if not is_korean:
            short = self._calc_short_metrics(info)
        else:
            short = {
                "shares_short":    0,
                "float_shares":    0,
                "short_pct_float": 0.0,
                "days_to_cover":   0.0,
                "borrow_rate_est": "N/A — 한국 주식은 KRX/DART API 필요",
            }
        result["short_metrics"] = short

        # Step 4: Squeeze Score 계산
        float_shares = short.get("float_shares", 0)
        score_data   = self._compute_squeeze_score(short, tech, float_shares)
        result.update(score_data)

        # Step 4.5: EV (기댓값) 산출
        sq_score = result["squeeze_score"]
        # 점수가 40 미만이면 스퀴즈 확률 5%, 40 이상부터는 최대 60%까지 증가
        if sq_score < 40:
            win_probability = 0.05
        else:
            win_probability = 0.05 + ((sq_score - 40) / 60.0) * 0.55
            
        win_probability = min(max(win_probability, 0.0), 1.0)
        
        # 단기 스퀴즈 성공 시 평균 기대수익 +50%, 실패 후 회귀 시 평균 손실 -20%
        avg_profit = 50.0  
        avg_loss = 20.0
        lose_probability = 1.0 - win_probability
        
        expected_value_pct = (win_probability * avg_profit) - (lose_probability * avg_loss)
        
        result["win_probability"] = round(win_probability, 4)
        result["avg_profit_pct"] = avg_profit
        result["avg_loss_pct"] = avg_loss
        result["expected_value_pct"] = round(expected_value_pct, 2)
        result["expected_value_note"] = f"EV: {expected_value_pct:.2f}% (승률 {win_probability:.1%})"

        # Step 5: 레벨 및 신호 결정 (임계값 내림차순 탐색)
        score = result["squeeze_score"]
        for threshold, (level, summary, signal) in sorted(SQUEEZE_LEVELS.items(), reverse=True):
            if score >= threshold:
                result["level"]   = level
                result["summary"] = summary
                result["signal"]  = signal
                break

        # Step 6: 위험 메모 자동 생성
        notes = []
        spf = short.get("short_pct_float", 0)
        dtc = short.get("days_to_cover",   0)
        vr  = tech.get("volume_ratio",     0)
        rsi = tech.get("rsi_14",           50)

        if spf >= THRESHOLDS["short_float_extreme"]:
            notes.append(f"공매도 비율 극단적({spf:.0%}) — 강제 커버링 위험")
        elif spf >= THRESHOLDS["short_float_high"]:
            notes.append(f"공매도 비율 높음({spf:.0%})")

        if dtc >= THRESHOLDS["days_to_cover_high"]:
            notes.append(f"커버 일수 {dtc:.1f}일 — 탈출 어려움")

        if vr >= THRESHOLDS["volume_surge_high"]:
            notes.append(f"거래량 {vr:.1f}배 급등 — 매수세 유입")

        if rsi < 30:
            notes.append(f"RSI {rsi:.0f} (극단적 과매도) — 반등 임박")
        elif rsi < 50:
            notes.append(f"RSI {rsi:.0f} (과매도권) — 숏에게 위험한 구간")

        if float_shares and float_shares < THRESHOLDS["float_micro"]:
            notes.append(f"극소형 플로트({float_shares / 1e6:.1f}M주) — 급등 잠재력 최대")
        elif float_shares and float_shares < THRESHOLDS["float_small"]:
            notes.append(f"소형 플로트({float_shares / 1e6:.1f}M주)")

        result["risk_note"] = " | ".join(notes) if notes else "특이 위험 없음"

        # Step 7: 옵션 감마 익스포저 (선택적)
        if include_options and not is_korean:
            print(f"  → 옵션 감마 익스포저 계산 중...")
            result["gamma"] = self._get_option_gamma_exposure(ticker, float_shares)

            # 감마스퀴즈 경고를 risk_note에 추가
            gep = result["gamma"].get("gamma_exposure_pct", 0)
            if gep >= THRESHOLDS["gamma_extreme"]:
                result["risk_note"] += f" | 🚨 감마 노출 {gep:.1f}% (감마스퀴즈 위험)"
        else:
            result["gamma"] = {"gamma_signal": "옵션 분석 생략 (스크리닝 모드 또는 한국 주식)"}

        # [SECURITY-MEDIUM] ENTER 신호 발생 시 실거래 연동 전 이중 확인 필수.
        # signal_generator → broker_interface 경유 시 paper_trading=True 기본값 유지.
        # 실거래 전환은 반드시 사용자 명시적 승인 후 broker_interface.py에서만 활성화할 것.
        print(f"  ✅ Squeeze Score: {score:.1f} | {result['level']}")
        return result

    def screen(
        self,
        tickers:         list,
        top_n:           int   = 10,
        min_score:       float = 40.0,
        include_options: bool  = False,  # 스크리닝 시 기본 비활성화 (속도 최적화)
    ) -> list:
        """
        워치리스트 종목 스크리닝 → Squeeze Score 순위 반환

        Args:
            tickers:         분석할 종목 코드 리스트
            top_n:           반환할 상위 종목 수
            min_score:       최소 Squeeze Score 필터 (이하 제거)
            include_options: 옵션 감마 계산 여부

        Returns:
            list[dict]: score 내림차순 정렬된 상위 종목 분석 결과
        """
        print(f"\n🔎 숏스퀴즈 스크리닝 시작: {len(tickers)}개 종목 분석 중...")
        results = []

        for ticker in tickers:
            try:
                r = self.analyze(ticker, include_options=include_options)
                if r["squeeze_score"] >= min_score:
                    results.append(r)
            except Exception as e:
                print(f"❌ [{ticker}] 스크리닝 실패: {e}")

        results.sort(key=lambda x: -x["squeeze_score"])
        print(f"\n✅ 스크리닝 완료: {len(results)}/{len(tickers)}개 종목이 최소점수 통과")
        return results[:top_n]

    def get_historical_short_interest(self, ticker: str) -> dict:
        """
        공매도 잔고 추이 분석 (현재 vs 전월 비교)

        Yahoo Finance는 2개 시점(현재 + 전월) 제공.
        정밀 이력이 필요하면 FINRA, Ortex, S3 Partners 등 유료 서비스 사용 권장.

        Returns:
            {current_short, prior_month_short, change, change_pct, trend, trend_signal}
        """
        try:
            info = yf.Ticker(ticker).info

            current  = int(info.get("sharesShort",            0) or 0)
            prior    = int(info.get("sharesShortPriorMonth",  0) or 0)
            change   = current - prior
            change_pct = change / prior if prior else 0.0

            if change > 0:
                trend = "INCREASING"
                trend_signal = f"⚠️ 공매도 잔고 {change_pct:+.1%} 증가 — 압력 누적 중"
            elif change < 0:
                trend = "DECREASING"
                trend_signal = f"✅ 공매도 잔고 {change_pct:+.1%} 감소 — 커버링 진행 중"
            else:
                trend = "FLAT"
                trend_signal = "➖ 전월 대비 변화 없음"

            return {
                "ticker":               ticker,
                "current_short":        current,
                "prior_month_short":    prior,
                "change":               change,
                "change_pct":           round(change_pct, 4),
                "trend":                trend,
                "trend_signal":         trend_signal,
                "data_note": "Yahoo Finance는 현재+전월 2개 시점만 제공. 정밀 이력은 Ortex/S3 권장.",
            }

        except Exception as e:
            return {"ticker": ticker, "error": str(e)}

    def get_market_overview(self, tickers: list) -> dict:
        """
        다수 종목의 공매도 환경 개요 — 시장 전체 숏 심리 파악용

        주요 지수 구성종목이나 섹터 ETF 내 종목들의 평균 공매도 수준을
        빠르게 파악하여 시장 센티먼트 판단에 활용.

        Returns:
            {avg_short_float, avg_days_to_cover, high_squeeze_count, tickers_data}
        """
        results = []
        for ticker in tickers:
            info = self._get_info(ticker)
            if not info:
                continue
            short = self._calc_short_metrics(info)
            results.append({
                "ticker":           ticker,
                "short_pct_float":  short["short_pct_float"],
                "days_to_cover":    short["days_to_cover"],
            })

        if not results:
            return {"error": "데이터 수집 실패"}

        avg_spf = np.mean([r["short_pct_float"] for r in results])
        avg_dtc = np.mean([r["days_to_cover"]   for r in results])
        high_sq = sum(1 for r in results if r["short_pct_float"] >= THRESHOLDS["short_float_high"])

        return {
            "scanned":               len(results),
            "avg_short_float_pct":   round(avg_spf, 4),
            "avg_days_to_cover":     round(avg_dtc, 2),
            "high_squeeze_count":    high_sq,
            "tickers_data":          results,
            "market_note": (
                "⚠️ 시장 전반적 공매도 높음 — 스퀴즈 연쇄 위험"
                if avg_spf > 0.15 else
                "✅ 시장 공매도 보통 수준"
            ),
        }


# ================================================================
# 단독 실행 테스트
# ================================================================

if __name__ == "__main__":
    analyzer = ShortSqueezeAnalyzer()

    # 1) 단일 종목 분석 (대표적 숏스퀴즈 후보)
    print("=" * 60)
    print("[테스트 1] 단일 종목 분석")
    result = analyzer.analyze("GME", include_options=False)
    print(f"\n  종목:         {result['ticker']}")
    print(f"  Squeeze Score: {result['squeeze_score']}")
    print(f"  레벨:          {result['level']}")
    print(f"  신호:          {result['signal']}")
    print(f"  요약:          {result['summary']}")
    print(f"  기댓값(EV):     {result.get('expected_value_note', '')}")
    print(f"  위험 메모:     {result['risk_note']}")

    c = result.get("short_metrics", {})
    print(f"\n  공매도 점유율: {c.get('short_pct_float', 0):.1%}")
    print(f"  커버 일수:    {c.get('days_to_cover', 0):.1f}일")
    print(f"  차입비용 추정: {c.get('borrow_rate_est', 'N/A')}")

    t = result.get("technical", {})
    print(f"\n  현재가:       ${t.get('current_price', 0):,.2f}")
    print(f"  거래량 배수:  {t.get('volume_ratio', 0):.2f}x")
    print(f"  RSI 14:       {t.get('rsi_14', 0):.1f}")
    print(f"  5일 모멘텀:   {t.get('mom_5d', 0):.2%}")

    # 2) 공매도 잔고 추이
    print("\n" + "=" * 60)
    print("[테스트 2] 공매도 잔고 추이")
    hist = analyzer.get_historical_short_interest("GME")
    print(f"  현재 잔고:   {hist.get('current_short', 0):,}주")
    print(f"  전월 잔고:   {hist.get('prior_month_short', 0):,}주")
    print(f"  변화율:      {hist.get('change_pct', 0):+.1%}")
    print(f"  추세:        {hist.get('trend_signal', '')}")

    # 3) 워치리스트 스크리닝
    print("\n" + "=" * 60)
    print("[테스트 3] 워치리스트 스크리닝")
    watchlist = ["GME", "AMC", "NVDA", "AAPL", "MSFT"]
    top = analyzer.screen(watchlist, top_n=3, min_score=30)
    for i, r in enumerate(top, 1):
        print(f"  {i}위: {r['ticker']:12s} Score={r['squeeze_score']:5.1f}  {r['level']}")
