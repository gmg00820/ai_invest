import pandas as pd
from datetime import datetime, timedelta
import sys
import os
import time
from tqdm import tqdm
from tabulate import tabulate
import FinanceDataReader as fdr

# 현재 디렉토리 모듈을 찾기 위해 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.screener import StockScreener
from src.market_data_stock import KISClient

def scan_full_market():
    client = KISClient()
    screener = StockScreener()
    
    today = datetime.now()
    today_str = today.strftime("%Y%m%d")
    start_date = (today - timedelta(days=150)).strftime("%Y%m%d")
    
    print("[INFO] KOSPI, KOSDAQ 전 종목 티커 수집 중 (FinanceDataReader)...")
    kospi_df = fdr.StockListing('KOSPI')
    kosdaq_df = fdr.StockListing('KOSDAQ')
    
    # KOSPI와 KOSDAQ 합치기
    all_stocks = pd.concat([kospi_df, kosdaq_df])
    
    # 우선선주(K 등), 펀드 등 제외를 원한다면 여기서 필터링 가능하지만 기본적으로 전부 담음
    all_tickers = all_stocks['Code'].tolist()
    ticker_to_name = dict(zip(all_stocks['Code'], all_stocks['Name']))
    
    print(f"[INFO] 총 {len(all_tickers)}개 종목을 발견했습니다.")
    
    # 너무 많은 요청을 방지하기 위해 사용자가 테스트 시에는 시총 상위 N개만 하거나 전체를 돌릴 수 있게 함
    # 전체를 돌리는 것도 가능하므로 일단 전 종목을 다 돌림
    # 주의: KIS API에서 2000개를 돌리면 시간이 약 2000 * 0.05 = 100초 (약 1.5분 정도 소요)
    tickers_data = {}
    
    print(f"\n[INFO] {start_date} ~ {today_str} 150일간의 주가 데이터를 다운로드합니다...")
    # TQDM progress bar 적용
    for ticker in tqdm(all_tickers, desc="Data Fetching"):
        name = ticker_to_name.get(ticker, ticker)
        
        # API 통신 (Rate limit 보호: 0.05초 대기 시 1초에 20건)
        try:
            df = client.get_daily_ohlcv(ticker, start_date, today_str)
            if df is not None and not df.empty:
                tickers_data[ticker] = {
                    "name": name,
                    "df": df
                }
        except Exception as e:
            pass # 패스
            
        time.sleep(0.05)
            
    if not tickers_data:
        print("수집된 데이터가 없습니다. API 연결 또는 토큰을 확인하세요.")
        return
        
    print("\n[Start] 조건 스크리닝 시작... (Naver News API는 1차 합격 종목에 대해서만 선별적으로 호출됩니다)")
    results_df = screener.run(tickers_data)
    
    print("\n" + "="*80)
    print("🏆 스크리닝 결과")
    print("="*80)
    
    if not results_df.empty:
        total_matched = len(results_df)
        print(f"[Result] 총 {total_matched}개 종목이 최소 1개 이상의 조건에서 점수를 획득했습니다.")
        
        # 50개가 넘어가면 점수 가장 높은 순 10개만 필터링
        if total_matched > 50:
            print("[INFO] 조건 일치 종목이 50개 이상이어서 점수 순위 TOP 10만 표시합니다.")
            final_df = results_df.head(10)
        else:
            final_df = results_df
            
        # 보기 불편한 터미널 출력을 tabulate를 사용해 예쁘게 표출
        print("\n" + tabulate(final_df, headers='keys', tablefmt='grid', showindex=False))
        
        # 파일 저장 (CSV, Excel)
        file_name = f"screening_results_{today_str}.xlsx"
        try:
            results_df.to_excel(file_name, index=False)
            print(f"\n[Success] 전체 검색 결과가 '{file_name}' 파일로 저장되었습니다. 이 엑셀 파일을 열어서 전체 스크리닝 결과를 편하게 확인하세요!")
        except Exception as e:
            results_df.to_csv(file_name.replace(".xlsx", ".csv"), index=False, encoding='utf-8-sig')
            print(f"\n[Success] 전체 검색 결과가 '{file_name.replace('.xlsx', '.csv')}' 파일로 저장되었습니다.")
            
    else:
        print("조건을 어떤 항목도 만족하지 않았습니다.")

if __name__ == "__main__":
    scan_full_market()
