"""
암호화폐 & 비트코인 데이터 수집기
===================================
- CoinGecko API (키 없이 무료 사용, 분당 10~30회)
- Alternative.me 공포탐욕지수 (무료)
- CoinCap API (무료, OHLCV)
- Blockchain.info (무료, 온체인 기초 지표)
"""

import requests
import time
from datetime import datetime, timedelta
from typing import Optional

# ==========================================
# CONFIGURATION
# ==========================================
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
COINCAP_BASE = "https://api.coincap.io/v2"
FEAR_GREED_URL = "https://api.alternative.me/fng/"
BLOCKCHAIN_BASE = "https://api.blockchain.info"
COINGECKO_RATE_DELAY = 1.5  # Free tier 분당 ~40회 이하


class CryptoDataCollector:
    """
    암호화폐 종합 데이터 수집기
    
    - CoinGecko: 가격, OHLCV, 마켓캡, 온체인 통계
    - Alternative.me: 공포탐욕지수 (Fear & Greed Index)
    - Blockchain.info: 비트코인 온체인 기초 지표
    
    Usage:
        collector = CryptoDataCollector()
        btc_price = collector.get_btc_current_price()
        fng = collector.get_fear_greed_index()
        ohlcv = collector.get_btc_ohlcv(days=365)
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'QuantDashboard/1.0'})

    def _get_coingecko(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """CoinGecko API 요청"""
        try:
            resp = self.session.get(
                f"{COINGECKO_BASE}/{endpoint}",
                params=params,
                timeout=15
            )
            time.sleep(COINGECKO_RATE_DELAY)
            
            if resp.status_code == 429:
                print("⚠️ CoinGecko Rate Limit. 60초 대기...")
                time.sleep(60)
                return self._get_coingecko(endpoint, params)
            
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"❌ CoinGecko Error [{endpoint}]: {e}")
            return None

    def get_btc_current_price(self) -> dict:
        """
        비트코인 현재 가격 및 기본 통계
        
        Returns:
            {
                'price_usd': 65432.0,
                'price_krw': 87000000,
                'market_cap': 1.28e12,
                'volume_24h': 4.5e10,
                'change_24h': -1.2,
                'ath': 73750.0,
                'ath_change_pct': -11.2,
            }
        """
        data = self._get_coingecko("coins/bitcoin", {
            'localization': 'false',
            'tickers': 'false',
            'market_data': 'true',
            'community_data': 'false',
            'developer_data': 'false',
        })
        
        if not data:
            return {}
        
        market = data.get('market_data', {})
        return {
            'price_usd': market.get('current_price', {}).get('usd', 0),
            'price_krw': market.get('current_price', {}).get('krw', 0),
            'market_cap_usd': market.get('market_cap', {}).get('usd', 0),
            'volume_24h_usd': market.get('total_volume', {}).get('usd', 0),
            'change_1h': market.get('price_change_percentage_1h_in_currency', {}).get('usd', 0),
            'change_24h': market.get('price_change_percentage_24h', 0),
            'change_7d': market.get('price_change_percentage_7d', 0),
            'change_30d': market.get('price_change_percentage_30d', 0),
            'change_1y': market.get('price_change_percentage_1y', 0),
            'ath_usd': market.get('ath', {}).get('usd', 0),
            'ath_change_pct': market.get('ath_change_percentage', {}).get('usd', 0),
            'ath_date': market.get('ath_date', {}).get('usd', ''),
            'circulating_supply': market.get('circulating_supply', 0),
            'max_supply': market.get('max_supply', 21000000),
            'total_volume': market.get('total_volume', {}).get('usd', 0),
            'last_updated': data.get('last_updated', ''),
        }

    def get_btc_ohlcv(self, days: int = 365, currency: str = "usd") -> list:
        """
        비트코인 OHLCV (Open/High/Low/Close/Volume) 데이터
        
        Args:
            days: 최근 N일 (1, 7, 14, 30, 90, 180, 365, 'max')
            currency: 'usd', 'krw', 'eur' 등
            
        Returns:
            [{'date': '2024-01-01', 'open': 42000, 'high': 43500, 'low': 41000, 'close': 43000, 'volume': 2.5e10}, ...]
        """
        data = self._get_coingecko(f"coins/bitcoin/ohlc", {
            'vs_currency': currency,
            'days': str(days),
        })
        
        if not data:
            return []
        
        results = []
        for candle in data:
            # CoinGecko OHLC: [timestamp_ms, open, high, low, close]
            ts, o, h, l, c = candle
            dt = datetime.fromtimestamp(ts / 1000)
            results.append({
                'date': dt.strftime('%Y-%m-%d'),
                'datetime': dt.isoformat(),
                'timestamp': ts,
                'open': o,
                'high': h,
                'low': l,
                'close': c,
            })
        
        return results

    def get_btc_market_chart(self, days: int = 365, currency: str = "usd") -> dict:
        """
        비트코인 상세 시계열 (가격 + 시총 + 거래량)
        
        Returns:
            {
                'prices': [(timestamp, price), ...],
                'market_caps': [(timestamp, cap), ...],
                'total_volumes': [(timestamp, vol), ...],
            }
        """
        data = self._get_coingecko(f"coins/bitcoin/market_chart", {
            'vs_currency': currency,
            'days': str(days),
            'interval': 'daily' if days > 90 else 'hourly',
        })
        
        if not data:
            return {'prices': [], 'market_caps': [], 'total_volumes': []}
        
        def convert(raw):
            return [{'date': datetime.fromtimestamp(ts/1000).strftime('%Y-%m-%d'), 'value': val} for ts, val in raw]
        
        return {
            'prices': convert(data.get('prices', [])),
            'market_caps': convert(data.get('market_caps', [])),
            'total_volumes': convert(data.get('total_volumes', [])),
        }

    def get_fear_greed_index(self, days: int = 30) -> list:
        """
        비트코인 공포탐욕지수 (Fear & Greed Index)
        - 0-24: Extreme Fear (극도 공포) → 강한 매수 신호
        - 25-49: Fear (공포)
        - 50: Neutral
        - 51-74: Greed (탐욕)
        - 75-100: Extreme Greed (극도 탐욕) → 매도 신호
        
        Returns:
            [{'date': '2024-01-01', 'value': 72, 'classification': 'Greed'}, ...]
        """
        try:
            resp = self.session.get(
                FEAR_GREED_URL,
                params={'limit': days, 'format': 'json'},
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            
            results = []
            for item in data.get('data', []):
                ts = int(item.get('timestamp', 0))
                results.append({
                    'date': datetime.fromtimestamp(ts).strftime('%Y-%m-%d') if ts else '',
                    'value': int(item.get('value', 50)),
                    'classification': item.get('value_classification', 'Neutral'),
                })
            
            return sorted(results, key=lambda x: x['date'])
        except Exception as e:
            print(f"❌ Fear & Greed Index Error: {e}")
            return []

    def get_crypto_market_overview(self, top_n: int = 20) -> list:
        """
        상위 N개 암호화폐 시장 현황
        
        Returns:
            [{'rank': 1, 'symbol': 'BTC', 'price': 65000, 'market_cap': 1.28e12, 'change_24h': -1.2}, ...]
        """
        data = self._get_coingecko("coins/markets", {
            'vs_currency': 'usd',
            'order': 'market_cap_desc',
            'per_page': top_n,
            'page': 1,
            'sparkline': 'false',
            'price_change_percentage': '1h,24h,7d',
        })
        
        if not data:
            return []
        
        results = []
        for coin in data:
            results.append({
                'rank': coin.get('market_cap_rank', 0),
                'id': coin.get('id', ''),
                'symbol': coin.get('symbol', '').upper(),
                'name': coin.get('name', ''),
                'price_usd': coin.get('current_price', 0),
                'market_cap': coin.get('market_cap', 0),
                'volume_24h': coin.get('total_volume', 0),
                'change_1h': coin.get('price_change_percentage_1h_in_currency', 0),
                'change_24h': coin.get('price_change_percentage_24h', 0),
                'change_7d': coin.get('price_change_percentage_7d_in_currency', 0),
                'ath': coin.get('ath', 0),
                'ath_change_pct': coin.get('ath_change_percentage', 0),
            })
        
        return results

    def get_btc_dominance(self) -> float:
        """
        비트코인 도미넌스 (%) - BTC 시총 / 전체 크립토 시총
        """
        data = self._get_coingecko("global")
        if data:
            return data.get('data', {}).get('market_cap_percentage', {}).get('btc', 0)
        return 0.0

    def get_global_crypto_stats(self) -> dict:
        """
        전체 암호화폐 시장 통계
        
        Returns:
            {
                'total_market_cap': ...,
                'total_volume_24h': ...,
                'btc_dominance': ...,
                'eth_dominance': ...,
                'defi_market_cap': ...,
                'active_cryptocurrencies': ...,
            }
        """
        data = self._get_coingecko("global")
        if not data:
            return {}
        
        d = data.get('data', {})
        return {
            'total_market_cap_usd': d.get('total_market_cap', {}).get('usd', 0),
            'total_volume_24h_usd': d.get('total_volume', {}).get('usd', 0),
            'btc_dominance': d.get('market_cap_percentage', {}).get('btc', 0),
            'eth_dominance': d.get('market_cap_percentage', {}).get('eth', 0),
            'active_cryptocurrencies': d.get('active_cryptocurrencies', 0),
            'markets': d.get('markets', 0),
            'market_cap_change_24h': d.get('market_cap_change_percentage_24h_usd', 0),
        }

    def get_coin_info(self, coin_id: str) -> dict:
        """
        특정 코인 상세 정보 (BTC, ETH, SOL 등)
        coin_id: 'bitcoin', 'ethereum', 'solana', 'ripple' 등
        """
        data = self._get_coingecko(f"coins/{coin_id}", {
            'localization': 'false',
            'tickers': 'false',
            'market_data': 'true',
            'community_data': 'true',
            'developer_data': 'false',
        })
        return data or {}


# ==========================================
# STANDALONE TEST
# ==========================================
if __name__ == "__main__":
    collector = CryptoDataCollector()
    
    print("[1] 비트코인 현재 가격...")
    price = collector.get_btc_current_price()
    print(f"    BTC/USD: ${price.get('price_usd', 0):,.2f}")
    print(f"    BTC/KRW: ₩{price.get('price_krw', 0):,.0f}")
    print(f"    24h 변동: {price.get('change_24h', 0):.2f}%")
    
    print("\n[2] 공포탐욕지수 (최근 7일)...")
    fng = collector.get_fear_greed_index(7)
    for f in fng[-3:]:
        print(f"    {f['date']}: {f['value']} ({f['classification']})")
    
    print("\n[3] 전체 크립토 시장...")
    global_stats = collector.get_global_crypto_stats()
    mc = global_stats.get('total_market_cap_usd', 0)
    print(f"    전체 시총: ${mc/1e12:.2f}T")
    print(f"    BTC 도미넌스: {global_stats.get('btc_dominance', 0):.1f}%")
