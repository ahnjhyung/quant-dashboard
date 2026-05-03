import yfinance as yf
import pandas as pd
import logging
from typing import Optional, List

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YF_Utils")

def download_ticker_data(ticker: str, start: str = "1970-01-01", end: Optional[str] = None) -> pd.DataFrame:
    """
    Download historical data for a single ticker using yfinance 1.3.0 (curl_cffi based).
    This version handles session/bypass automatically, so we don't pass a custom requests session.
    """
    try:
        # yfinance 1.3.0 handles the bypass automatically. 
        # Just use Ticker or yf.download directly with proxy if needed.
        # Here we use the standard download which the fork has patched.
        df = yf.download(ticker, start=start, end=end, progress=False)
        
        if df.empty:
            logger.warning(f"No data returned for {ticker} from {start}.")
            return pd.DataFrame()
            
        # Clean up columns (multi-index handling)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # Standardize index
        df.index = pd.to_datetime(df.index).tz_localize(None)
        logger.info(f"Successfully downloaded {len(df)} rows for {ticker}.")
        return df
    except Exception as e:
        logger.error(f"Failed to download {ticker}: {str(e)}")
        return pd.DataFrame()

def download_multiple_tickers(tickers: List[str], start: str = "1970-01-01") -> pd.DataFrame:
    """Download and merge multiple tickers into a single Close price DataFrame."""
    combined = pd.DataFrame()
    for t in tickers:
        df = download_ticker_data(t, start=start)
        if not df.empty:
            combined[t] = df['Close']
    return combined.dropna(how='all')
