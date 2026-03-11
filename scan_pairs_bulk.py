import pandas as pd
from analysis.pairs_trading import PairsTradingAnalyzer
import json

def scan_multiple_pairs():
    analyzer = PairsTradingAnalyzer()
    
    # 분석할 페어 리스트 (유사 업종 / 동조화 자산 위주)
    pairs_to_test = [
        # 미국 기술주 주도주 페어
        ("GOOGL", "META", "미국 인터넷/광고"),
        ("NVDA", "AMD", "미국 반도체"),
        ("MSFT", "AAPL", "미국 빅테크 대장"),
        ("QQQ", "XLK", "기술주 ETF"),
        
        # 한국 금융/지주사 (공적분 잘 나오는 전형적 가치주 섹터)
        ("105560.KS", "055550.KS", "한국 금융 (KB vs 신한)"),
        ("086790.KS", "316140.KS", "한국 금융 (하나 vs 우리)"),
        ("005930.KS", "000660.KS", "한국 반도체 (삼성전자 vs SK하이닉스)"),
        ("005380.KS", "000270.KS", "한국 자동차 (현대차 vs 기아)"),
        
        # 암호화폐 및 매크로 우회 자산
        ("BTC-USD", "ETH-USD", "암호화폐 대장주"),
        ("GLD", "SLV", "귀금속 (금 vs 은)"),
    ]
    
    results = []
    
    print("=== 다중 자산 상관계수 및 공적분 EV 스캔 시작 ===")
    for y_ticker, x_ticker, category in pairs_to_test:
        try:
            res = analyzer.analyze_pair(y_ticker, x_ticker, period="3y")
            if 'error' not in res:
                res['category'] = category
                results.append(res)
                print(f"[OK] {category}: {res['pair']} -> 상관계수: {res['correlation']:.2f}, 공적분(p-value): {res['coint_pvalue']:.3f}, EV: {res['risk_metrics']['expected_value_pct']:.4f}")
            else:
                print(f"[FAIL] {category}: {y_ticker} vs {x_ticker} -> {res['error']}")
        except Exception as e:
            print(f"[ERROR] {category}: {y_ticker} vs {x_ticker} -> {e}")

    # 공적분(유의수준 10% 이내)이거나 상관계수가 높은 순으로 정렬
    results.sort(key=lambda x: x['coint_pvalue'])
    
    print("\n\n=== 🏆 최상위 퀀트 페어 트레이딩 후보 (공적분 p-value 0.05 미만 유의) ===")
    
    valid_pairs = [r for r in results if r['is_cointegrated'] or r['coint_pvalue'] < 0.10]
    
    if not valid_pairs:
         print(" 통계적으로 완벽히 유의미한(장기 균형) 페어를 찾지 못했습니다. 그러나 단기 상관계수가 높은 종목들은 다음과 같습니다.")
         valid_pairs = sorted(results, key=lambda x: abs(x['correlation']), reverse=True)[:3]
         
    for r in valid_pairs:
        print(f"\n[{r['category']}] {r['pair']}")
        print(f" └ 상관계수(Correlation)  : {r['correlation']:.4f} (1에 가까울수록 같은 방향 움직임)")
        print(f" └ 공적분(Cointegration) p-value : {r['coint_pvalue']:.4f} {'(완전 유의함 🌟)' if r['is_cointegrated'] else '(다소 약함)'}")
        print(f" └ 헤지 비율(Hedge Beta) : {r['hedge_ratio_beta']:.4f}")
        print(f" └ 현재 갭(Z-Score)      : {r['current_z_score']:.2f} -> 분석 신호: {r['signal']} ({r['reason']})")
        print(f" └ 📊 모델 기대 기댓값(EV)  : 승률 {r['risk_metrics']['win_probability']*100:.1f}% | 예상 이익 {r['risk_metrics']['avg_profit_pct']*100:.2f}% | 예상 손실 {-r['risk_metrics']['expected_value_pct']*0-1.5*0.01:.2f}% (임시) -> **실제 기댓값(EV): {r['risk_metrics']['expected_value_pct']*100:.4f}%**")
        
    # 파일로 리포팅용 덤프
    with open("coint_scan_results.json", "w", encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    scan_multiple_pairs()
