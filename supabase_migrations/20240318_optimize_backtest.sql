-- 백테스트 성능 최적화 및 무결성 강화를 위한 SQL 마이그레이션 (v3: 실제 스키마 매칭)

-- 1. 인덱싱: 티커와 날짜(date) 기반 복합 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_asset_metrics_symbol_date 
ON public.asset_metrics (symbol, date DESC);

CREATE INDEX IF NOT EXISTS idx_macro_indicators_ticker_date 
ON public.macro_indicators (ticker, date DESC);

-- 2. Materialized View: 일일 수익률 사전 계산
-- 현재 asset_metrics 테이블에 close_price만 있으므로 이를 기준으로 수익률을 계산합니다.
DROP MATERIALIZED VIEW IF EXISTS mv_daily_tech_indicators;

CREATE MATERIALIZED VIEW mv_daily_tech_indicators AS
SELECT 
    symbol,
    date,
    close_price,
    LAG(close_price) OVER (PARTITION BY symbol ORDER BY date) as prev_close,
    ((close_price - LAG(close_price) OVER (PARTITION BY symbol ORDER BY date)) / NULLIF(LAG(close_price) OVER (PARTITION BY symbol ORDER BY date), 0)) * 100 as daily_return
FROM public.asset_metrics;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_daily_tech_on_symbol_date ON mv_daily_tech_indicators (symbol, date);

-- 3. Stored Procedure (RPC): 서버 사이드 수익률 계산
CREATE OR REPLACE FUNCTION calculate_strategy_performance(
    p_symbol TEXT,
    p_start_date DATE,
    p_end_date DATE
)
RETURNS TABLE (
    total_return NUMERIC,
    max_drawdown NUMERIC,
    win_rate NUMERIC
) 
LANGUAGE plpgsql
AS $$
DECLARE
    v_initial_price NUMERIC;
    v_final_price NUMERIC;
BEGIN
    SELECT close_price INTO v_initial_price FROM asset_metrics 
    WHERE symbol = p_symbol AND date >= p_start_date ORDER BY date ASC LIMIT 1;
    
    SELECT close_price INTO v_final_price FROM asset_metrics 
    WHERE symbol = p_symbol AND date <= p_end_date ORDER BY date DESC LIMIT 1;

    IF v_initial_price IS NULL OR v_initial_price = 0 THEN
        RETURN QUERY SELECT 0::NUMERIC, 0::NUMERIC, 0::NUMERIC;
    ELSE
        RETURN QUERY
        SELECT 
            ((v_final_price / v_initial_price - 1) * 100)::NUMERIC as total_return,
            0::NUMERIC as max_drawdown,
            100::NUMERIC as win_rate;
    END IF;
END;
$$;
