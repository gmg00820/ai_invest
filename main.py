import time
import datetime
import pandas as pd
import FinanceDataReader as fdr
from src.market_data_upbit import get_krw_tickers, get_daily_ohlcv as get_upbit_ohlcv
from src.market_data_stock import KISClient
from src.technical_filters import filter_asset
from src.news_analyzer import fetch_recent_news, analyze_sentiment
from src.scenario_generator import generate_trading_scenario

def run_crypto_scanner():
    print("=== 암호화폐(Upbit) 스윙 종목 스캔 시작 ===")
    tickers = get_krw_tickers()
    found_assets = []
    
    # 빠른 테스트를 위해 상위/특정 갯수로 제한 가능. 모두 스캔하려면 tickers 전체
    # 여기서는 시간 관계상 앞의 150위 이내 주요 코인만 탐색
    for i, ticker in enumerate(tickers[:150]):
        print(f"[{i+1}/{min(150, len(tickers))}] 스캔 중: {ticker}", end="\r")
        df = get_upbit_ohlcv(ticker, count=60)
        time.sleep(0.12) # Rate limit 방지 (Upbit API 초당 10회 제한 이하로)
        
        is_passed, tech_data = filter_asset(df)
        if is_passed:
            print(f"\n[!] 조건 부합 종목 발견: {ticker}")
            # 뉴스 분석
            news = fetch_recent_news(ticker)
            sentiment = analyze_sentiment(ticker, news)
            
            # 시나리오 생성
            scenario = generate_trading_scenario(ticker, tech_data['current_price'], tech_data, sentiment)
            
            found_assets.append({
                "ticker": ticker,
                "type": "Crypto",
                "price": tech_data['current_price'],
                "tech": tech_data,
                "sentiment": sentiment,
                "scenario": scenario
            })
    print("\n=== 암호화폐 스캔 완료 ===\n")
    return found_assets

def run_stock_scanner():
    print("=== 국내주식(한국투자증권 API) 스윙 종목 스캔 시작 ===")
    kis = KISClient()
    if not kis.access_token:
        print("KIS API 키가 없거나 토큰 발급에 실패. (주식 스캔 건너뜀)")
        return []
        
    try:
        krx = fdr.StockListing('KRX')
        # 보통주, KOSPI/KOSDAQ 시가총액 상위 150종목으로 대상 한정 (API Limit 문제 및 시간 관계)
        krx = krx[krx['Market'].isin(['KOSPI', 'KOSDAQ'])]
        krx_target = krx.head(150)
        tickers = krx_target['Code'].tolist()
        names = krx_target['Name'].tolist()
    except Exception as e:
        print(f"종목 리스트 수집 실패: {e}")
        return []
        
    found_assets = []
    end_date = datetime.datetime.now().strftime("%Y%m%d")
    start_date = (datetime.datetime.now() - datetime.timedelta(days=100)).strftime("%Y%m%d")
    
    for i, (ticker, name) in enumerate(zip(tickers, names)):
        print(f"[{i+1}/{len(tickers)}] 스캔 중: {name} ({ticker})", end="\r")
        df = kis.get_daily_ohlcv(ticker, start_date, end_date)
        time.sleep(0.06) # KIS API limit 20 req/sec
        
        is_passed, tech_data = filter_asset(df)
        if is_passed:
            print(f"\n[!] 조건 부합 종목 발견: {name} ({ticker})")
            news = fetch_recent_news(name)
            sentiment = analyze_sentiment(name, news)
            scenario = generate_trading_scenario(name, tech_data['current_price'], tech_data, sentiment)
            
            found_assets.append({
                "ticker": f"{name} ({ticker})",
                "type": "Stock",
                "price": tech_data['current_price'],
                "tech": tech_data,
                "sentiment": sentiment,
                "scenario": scenario
            })
            
    print("\n=== 국내주식 스캔 완료 ===\n")
    return found_assets

def main():
    print("🚀 스윙 트레이딩 발굴 에이전트 시작 🚀\n")
    
    crypto_results = run_crypto_scanner()
    stock_results = run_stock_scanner()
    
    all_results = crypto_results + stock_results
    
    report = "# 📈 스윙 종목 발굴 최종 리포트\n\n"
    report += f"**생성 일시:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    report += f"**선별된 종목 수:** {len(all_results)}개\n\n"
    
    if not all_results:
        report += "오늘은 사용자님의 조건(20일선 위, 거래대금 500억 이상 등)을 모두 만족하는 종목이 없습니다.\n"
    else:
        for idx, item in enumerate(all_results):
            report += f"---\n\n## {idx+1}. {item['ticker']} [{item['type']}]\n"
            report += f"- **현재가:** {item['price']:,.0f}\n"
            report += f"- **기술지표 타점(Envelope):** 하단 {item['tech']['envelope'].get('env_lower', 0):,.0f} | 중심 {item['tech']['envelope'].get('env_center', 0):,.0f} | 상단 {item['tech']['envelope'].get('env_upper', 0):,.0f}\n"
            report += f"- **엘리어트 파동 근사치:** {item['tech']['wave'].get('wave_status', 'N/A')} (점수: {item['tech']['wave'].get('score', 0)})\n"
            report += f"- **뉴스 감성:** {item['sentiment'].get('sentiment', 'Neutral')} (Point: {item['sentiment'].get('score', 50)})\n"
            report += f"  - *{item['sentiment'].get('summary', '')}*\n\n"
            report += f"### 💡 AI 생성 시나리오 및 대응 전략\n{item['scenario']}\n\n"
            
    with open("swing_report.md", "w", encoding="utf-8") as f:
        f.write(report)
        
    print(f"\n✅ 리포트 생성 완료: 총 {len(all_results)} 종목이 swing_report.md 에 저장되었습니다.")

if __name__ == "__main__":
    main()
