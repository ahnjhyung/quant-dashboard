import sys
import io
import os
import certifi
import traceback
from pathlib import Path
from dotenv import load_dotenv

# 인증서 경로를 certifi로 명시적 지정
os.environ['CURL_CA_BUNDLE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

# .env 명시적 절대경로 로드
load_dotenv(Path(__file__).parent / '.env')

from analysis.entry_timing import EntryTimingEngine
from data_collectors.supabase_manager import SupabaseManager

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

print("=== [PHASE 6] Backend Integration Verification ===\n")

# 1. Supabase Manager Test
print("[Test 1] SupabaseManager - Fetching Regime Risk Score")
try:
    db = SupabaseManager()
    score = db.get_regime_risk_score()
    print(f"✅ Success! Retrieved Regime Risk Score: {score}")
    
    insight = db.get_latest_rag_insight()
    print(f"✅ Success! Retrieved RAG Insight (Length: {len(insight)})")
    if insight:
        print(f"   Excerpt: {insight[:100]}...")
except Exception as e:
    print(f"❌ Failed Test 1: {e}")
    traceback.print_exc()
    sys.exit(1)

# 2. EntryTimingEngine Test (incorporating the new penalty logic)
print("\n[Test 2] EntryTimingEngine - Checking Kelly Sizing with Penalty")
try:
    engine = EntryTimingEngine()
    result = engine.analyze_entry("AAPL", "us_stock")
    
    if "position_sizing" in result:
        sizing = result["position_sizing"]
        print(f"✅ Success! Position Sizing logic executed.")
        print(f"   - Target Asset: {result.get('ticker')}")
        print(f"   - Regime Risk Score: {sizing.get('regime_risk_score', 'N/A')}")
        print(f"   - Base Win Prob: {sizing.get('base_win_prob', 'N/A')}")
        print(f"   - Adjusted Kelly %: {sizing.get('recommended_pct', 0)}%")
        if sizing.get('risk_adjusted'):
            print(f"   - 🚨 ADJUSTMENT NOTE: {sizing.get('note')}")
        else:
            print("   - No penalty adjustment applied.")
    else:
        print("❌ Failed Test 2: 'position_sizing' missing entirely.")
        sys.exit(1)
        
except Exception as e:
    print(f"❌ Failed Test 2: {e}")
    traceback.print_exc()
    sys.exit(1)

print("\n🎉 All tests passed. The Phase 6 RAG integration logic is sound.")
