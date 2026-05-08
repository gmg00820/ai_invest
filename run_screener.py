import pandas as pd
from datetime import datetime, timedelta
import sys
import os

# 현재 디렉토리 모듈을 찾기 위해 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.screener import StockScreener
from src.market_data_stock import KISClient

def run_example():
    client = KISClient()
    screener = StockScreener()
    
    # 예시 종목 (테스트를 위해 몇 개 종목만 임의로 구성)
    # 실제로는 전체 종목 코드를 가져와서 반복문을 돌리거나, 특정 섹터를 필터링함.
    target_tickers = {
        "005930": "삼성전자",
        "000660": "SK하이닉스",
        "035420": "NAVER",
        "035720": "카카오",
        "005380": "현대차",
        "028300": "HLB"
    }
    
    today = datetime.now()
    start_date = (today - timedelta(days=150)).strftime("%Y%m%d") # 지표 계산에 필요한 여유 확보
    end_date = today.strftime("%Y%m%d")
    
    tickers_data = {}
    print("[INFO] 데이터 수집 중...")
    for ticker, name in target_tickers.items():
        print(f"[{name}] 데이터 수집...")
        df = client.get_daily_ohlcv(ticker, start_date, end_date)
        if df is not None and not df.empty:
            tickers_data[ticker] = {
                "name": name,
                "df": df
            }
        else:
            print(f"  [Error] {name} 데이터 수집 실패")
            
    if not tickers_data:
        print("수집된 데이터가 없습니다. API 연결 또는 토큰을 확인하세요.")
        return
        
    print("\n[Start] 스크리닝 시작...")
    # target_date_idx = -1 이면 가장 최근 거래일자 기준 (기본 설정값)
    results = screener.run(tickers_data)
    
    print("\n" + "="*80)
    print("[Result] 스크리닝 결과 (점수 순 랭킹)")
    print("="*80)
    
    if not results.empty:
        # 데이터프레임 출력을 보기 좋게 설정
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        print(results.to_string(index=False))
    else:
        print("조건을 어떤 항목도 만족하지 않았습니다.")

if __name__ == "__main__":
    run_example()
