/**
 * [Quant System - Data Collector] Phase 1: The Gatherer
 * - Role: Fetch global asset prices, macroeconomic data, and news sentiment, then store them in Supabase.
 * - This script is meant to be run daily via a time-driven trigger in Google Apps Script.
 */

const CONFIG = {
  // [1] Supabase
  SB_URL: 'https://fcuenflxkkpyplehsizg.supabase.co',
  SB_KEY: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZjdWVuZmx4a2tweXBsZWhzaXpnIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2OTUxNTk2OCwiZXhwIjoyMDg1MDkxOTY4fQ.Ic-Hc8j67bkYsUKTmcbwh5RwjI84PNS6W75lkW_bnEs',

  // [2] Korea Investment & Securities (KIS)
  KIS_APP_KEY: 'PSP9QxxytJyUimz3TDfwUDkW3dZhe2fuEqnf',
  KIS_APP_SECRET: 'SFiLtTEk0XdWhE2x+ta+HEhpPbYQiIa6V0KisWMzXrgJzBL5sQHU96LeCTy2bHVYo5e8N7iXcx7NbxL/O80apGFgacoYDwxPe53tFkw51ontrrYFRNzqWFSlwPINDUwCSkXBtBMRTQ0v8G9f96hWdWJHuDwurhhvV2Gl1wa0+L4EgFAJOXY=',
  KIS_URL: 'https://openapi.koreainvestment.com:9443',

  // [3] FRED (Macro)
  FRED_KEY: '205c05307eead18175559e5dfe7e7025',
  
  // [4] ECOS (Macro - KR)
  ECOS_KEY: "VQEJAS8MON6ZLZ3NL7PS",

  // [5] Target Universe
  US_TICKERS: ['SPY', 'QQQ', 'SOXX', 'TQQQ', 'SQQQ', 'TLT', 'DIA'], // 금, 비트코인 등은 FMP나 야후파이낸스로 분리
  KR_TICKERS: ['069500', '252670', '360200', '304940', '267440'],
  
  // Mapping KR Codes to readable Symbols for Supabase
  KR_SYMBOL_MAP: {
    '069500': 'KOSPI200',
    '252670': 'KOSPI_INV2X',
    '360200': 'SPY_H',
    '304940': 'QQQ_H',
    '267440': 'TLT_H'
  },
  
  // [NEW] Yahoo Finance Tickers (for Crypto & Commodities & Global Indices)
  YAHOO_TICKERS: [
    'BTC-USD', // 비트코인
    'GC=F',    // 금 선물
    'CL=F',    // WTI 원유 선물
    '^GSPC',   // S&P 500 지수
    '^IXIC',   // 나스닥 종합 지수
    'DX-Y.NYB' // 달러 인덱스 (DXY 대체, 실시간 확인용)
  ],

  FRED_TICKERS: [
    'T10Y2Y',       // Yield Spread
    'VIXCLS',       // VIX
    'DEXKOUS',      // KRW/USD Exchange Rate
    'BAMLH0A0HYM2', // High Yield Spread
    'TEDRATE',      // TED Spread
    'STLFSI3',      // Financial Stress Index
    'DGS2',         // US 2Y Treasury
    'DGS10',        // US 10Y Treasury
    'FEDFUNDS',     // Fed Funds Rate
    'UNRATE',       // Unemployment
    'DTWEXBGS',     // DXY (Broad Dollar Index) 
    'M2SL',         // M2 Liquidity
    'INDPRO',       // Industrial Production
    'WALCL',        // Fed Total Assets
    'WTREGEN',      // TGA
    'RRPONTSYD',    // RRP
    
    // [NEW] 매크로 지표 추가
    'CPALTT01USM657N', // 미국 CPI (인플레이션 지표)
    'BAMLH0A0HYM2EY',  // US High Yield Effective Yield (하이일드 실효 수익률)
    'T5YIE',           // 5-Year Breakeven Inflation Rate (5년 기대 인플레이션)
    'NFCI',            // Chicago Fed National Financial Conditions Index (금융환경지수)
    'PCEPI'            // PCE 물가지수 (연준이 가장 선호하는 인플레이션 보조지표)
  ]
};

// ==========================================
// [MAIN FUNCTION] Triggered Daily
// ==========================================
function runDataCollector() {
  console.log("--- 🚀 [Data Collector] Starting daily fetch ---");
  const todayKR = Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd");
  
  try {
    const kisToken = getKisAccessToken(); 

    // 1. Fetch US Stocks (KIS)
    CONFIG.US_TICKERS.forEach(sym => {
       fetchKisUSPrice(kisToken, sym, todayKR);
       Utilities.sleep(300);
    });

    // 2. Fetch KR Stocks (KIS)
    CONFIG.KR_TICKERS.forEach(code => {
      fetchKisKRPrice(kisToken, code, todayKR);
      Utilities.sleep(300);
    });

    // [NEW] 2.5 Fetch Yahoo Finance Data (Crypto, Commodities, Indices)
    CONFIG.YAHOO_TICKERS.forEach(sym => {
      fetchYahooFinanceAsset(sym, todayKR);
      Utilities.sleep(300);
    });

    // 3. News Sentiment (Google News RSS)
    // 야후 티커(비트코인 등)도 뉴스 수집 목록에 포함
    const newsTargets = [...CONFIG.US_TICKERS, 'BTC', 'Gold', 'WTI Crude']; 
    newsTargets.forEach(sym => {
       fetchGoogleNews(sym, todayKR);
       Utilities.sleep(300);
    });

    // 4. Macro Data (FRED)
    processFredData(todayKR);
    
    // 5. Macro Data (ECOS - Korea Base Rate)
    const krRate = fetchEcosBaseRate();
    if (krRate) {
       callSupabaseRpc("upsert_macro", { p_date: todayKR, p_ticker: 'KR_BASE_RATE', p_value: krRate });
    }

    console.log("--- ✅ [Data Collector] Finished successfully ---");
  } catch (e) {
    console.error("❌ Collector Error: " + e.message);
  }
}

// ==========================================
// [DATA FETCH FUNCTIONS]
// ==========================================

function fetchKisUSPrice(token, symbol, date) {
  let excd = 'NAS';
  if (['SPY', 'GLD', 'TLT', 'DIA'].includes(symbol)) excd = 'AMS';
  const url = `${CONFIG.KIS_URL}/uapi/overseas-price/v1/quotations/price?AUTH=&EXCD=${excd}&SYMB=${symbol}`;
  try {
    const res = JSON.parse(UrlFetchApp.fetch(url, {
      "headers": { "authorization": token, "appkey": CONFIG.KIS_APP_KEY, "appsecret": CONFIG.KIS_APP_SECRET, "tr_id": "HHDFS00000300" },
      "muteHttpExceptions": true
    }).getContentText());
    if (res.output && res.output.last) {
      callSupabaseRpc("upsert_asset", { p_date: date, p_symbol: symbol, p_close_price: parseFloat(res.output.last) });
      console.log(`[US] ${symbol}: $${res.output.last}`);
    }
  } catch (e) { console.error(`[US Fail] ${symbol}`); }
}

function fetchKisKRPrice(token, code, date) {
  const url = `${CONFIG.KIS_URL}/uapi/domestic-stock/v1/quotations/inquire-price?FID_COND_MRKT_DIV_CODE=J&FID_INPUT_ISCD=${code}`;
  try {
    const res = JSON.parse(UrlFetchApp.fetch(url, {
      "headers": { "authorization": token, "appkey": CONFIG.KIS_APP_KEY, "appsecret": CONFIG.KIS_APP_SECRET, "tr_id": "FHKST01010100" },
      "muteHttpExceptions": true
    }).getContentText());
    if (res.output && res.output.stck_prpr) {
      const symbol = CONFIG.KR_SYMBOL_MAP[code] || code;
      callSupabaseRpc("upsert_asset", { p_date: date, p_symbol: symbol, p_close_price: parseFloat(res.output.stck_prpr) });
      console.log(`[KR] ${symbol}: ₩${res.output.stck_prpr}`);
    }
  } catch (e) { console.error(`[KR Fail] ${code}`); }
}

// [NEW] Yahoo Finance Fetcher for Crypto & Commodities (Since KIS might not natively support them easily)
function fetchYahooFinanceAsset(symbol, date) {
  // Yahoo Finance sometimes requires URL encoding for symbols like ^GSPC
  const encodedSymbol = encodeURIComponent(symbol);
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodedSymbol}?interval=1d&range=1d`;
  try {
    const res = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
    const json = JSON.parse(res.getContentText());
    if (json.chart && json.chart.result && json.chart.result.length > 0) {
      const result = json.chart.result[0];
      
      let closePrice = null;
      // Depending on the asset, the close price might be in regularMarketPrice or inside the indicators array
      if (result.meta && result.meta.regularMarketPrice !== undefined) {
        closePrice = result.meta.regularMarketPrice;
      } else if (result.indicators && result.indicators.quote && result.indicators.quote.length > 0) {
        const quotes = result.indicators.quote[0].close;
        if (quotes && quotes.length > 0) {
           // Get the last valid close price
           closePrice = quotes.filter(p => p !== null).pop();
        }
      }

      if (closePrice !== null && closePrice !== undefined) {
        callSupabaseRpc("upsert_asset", { p_date: date, p_symbol: symbol, p_close_price: parseFloat(closePrice) });
        console.log(`[Yahoo] ${symbol}: $${parseFloat(closePrice).toFixed(2)}`);
      } else {
        console.warn(`[Yahoo Warn] ${symbol} parsed but no close price found.`);
      }
    } else {
        console.warn(`[Yahoo Warn] ${symbol} empty result structure. res: ${res.getContentText()}`);
    }
  } catch(e) { console.error(`[Yahoo Fail] ${symbol}`, e.message); }
}

function fetchGoogleNews(symbol, today) {
  const query = encodeURIComponent(`${symbol} stock news`);
  const url = `https://news.google.com/rss/search?q=${query}&hl=en-US&gl=US&ceid=US:en`;
  try {
    const xml = UrlFetchApp.fetch(url, {muteHttpExceptions: true}).getContentText();
    const document = XmlService.parse(xml);
    const items = document.getRootElement().getChild('channel').getChildren('item');
    
    if (items && items.length > 0) {
      let totalScore = 0;
      let buzzVolume = 0;
      let topTitle = items[0].getChild('title').getText();

      const maxItems = Math.min(items.length, 20);
      for(let i = 0; i < maxItems; i++) {
        const title = items[i].getChild('title').getText().toLowerCase();
        let score = 0.1;
        if (title.match(/soar|jump|surge|beat|record|high|buy|upgrade|gain|profit|deal/)) score = 0.7;
        else if (title.match(/plunge|drop|dive|miss|fail|low|sell|downgrade|loss|lawsuit|crash/)) score = -0.7;
        
        totalScore += score;
        buzzVolume += 1;
      }
      
      // Calculate average score
      const avgScore = totalScore / buzzVolume;

      callSupabaseRpc("upsert_news", { 
        p_date: today, 
        p_symbol: symbol, 
        p_score: avgScore, 
        p_volume: buzzVolume, 
        p_title: topTitle 
      });
      console.log(`[News] ${symbol}: Score ${avgScore.toFixed(2)} (${buzzVolume} items)`);
    }
  } catch (e) { console.warn(`[News Error] ${symbol}`); }
}

function processFredData(fallbackDate) {
  CONFIG.FRED_TICKERS.forEach(t => {
    try {
      const res = JSON.parse(UrlFetchApp.fetch(`https://api.stlouisfed.org/fred/series/observations?series_id=${t}&api_key=${CONFIG.FRED_KEY}&file_type=json&sort_order=desc&limit=1`, {muteHttpExceptions:true}).getContentText());
      if(res.observations && res.observations.length > 0) {
        let val = parseFloat(res.observations[0].value);
        if (isNaN(val)) val = 0; // fallback if data is "."
        
        callSupabaseRpc("upsert_macro", { 
            p_date: res.observations[0].date || fallbackDate, 
            p_ticker: t, 
            p_value: val 
        });
        console.log(`[Macro] ${t}: ${val}`);
      }
    } catch(e) {}
    Utilities.sleep(200);
  });
}

function fetchEcosBaseRate() {
  const now = new Date();
  const todayStr = Utilities.formatDate(now, "GMT+9", "yyyyMMdd");
  const past = new Date(); past.setDate(now.getDate() - 90); 
  const startStr = Utilities.formatDate(past, "GMT+9", "yyyyMMdd");
  try {
    const url = `http://ecos.bok.or.kr/api/StatisticSearch/${CONFIG.ECOS_KEY}/json/kr/1/100/722Y001/D/${startStr}/${todayStr}/0101000/`;
    const res = UrlFetchApp.fetch(url, {muteHttpExceptions: true});
    const json = JSON.parse(res.getContentText());
    if (json.StatisticSearch && json.StatisticSearch.row) {
      return parseFloat(json.StatisticSearch.row.pop().DATA_VALUE);
    }
  } catch(e) {}
  return null;
}

// ==========================================
// [UTILITY FUNCTIONS]
// ==========================================

function getKisAccessToken() {
  const res = JSON.parse(UrlFetchApp.fetch(`${CONFIG.KIS_URL}/oauth2/tokenP`, {
    "method": "post", "contentType": "application/json", "muteHttpExceptions": true,
    "payload": JSON.stringify({ "grant_type": "client_credentials", "appkey": CONFIG.KIS_APP_KEY, "appsecret": CONFIG.KIS_APP_SECRET })
  }).getContentText());
  return "Bearer " + res.access_token;
}

function callSupabaseRpc(fn, payload) {
  UrlFetchApp.fetch(`${CONFIG.SB_URL}/rest/v1/rpc/${fn}`, { 
    "method": "post", 
    "headers": { "apikey": CONFIG.SB_KEY, "Authorization": "Bearer " + CONFIG.SB_KEY, "Content-Type": "application/json" }, 
    "payload": JSON.stringify(payload),
    "muteHttpExceptions": true
  });
}
