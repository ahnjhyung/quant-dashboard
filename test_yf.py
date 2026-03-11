import yfinance as yf
import requests
import os

# SSL 인증서 문제를 회피하기 위해 verify=False 설정 (백테스트 데이터 수집용이므로 안전함)
# 또는 certifi 경로를 수동으로 지정할 수 없으므로 requests의 세션을 조작함
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

old_init = requests.Session.__init__
def new_init(self, *args, **kwargs):
    old_init(self, *args, **kwargs)
    self.verify = False
requests.Session.__init__ = new_init

def test_download():
    ticker = "SPY"
    print(f"Testing download for {ticker}...")
    try:
        data = yf.download(ticker, period="1mo", progress=False)
        if not data.empty:
            print(f"Success! Downloaded {len(data)} rows.")
            print(data.tail())
        else:
            print("Failed: Empty DataFrame")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_download()
