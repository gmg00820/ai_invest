import os
import glob
import re
import pickle
import pandas as pd
import numpy as np
import FinanceDataReader as fdr
import time

# 1. market_data_cache_20260615.pkl 로드
cache_file = "market_data_cache_20260615.pkl"
tickers_data = {}
if os.path.exists(cache_file):
    print("Loading market data cache...")
    try:
        with open(cache_file, "rb") as f:
            tickers_data = pickle.load(f)
        print(f"Loaded {len(tickers_data)} stocks from cache.")
    except Exception as e:
        print(f"Failed to load cache: {e}")
else:
    print("Cache file not found, will fetch all data from FDR.")

# 2. screening_results_*.csv 파일 목록 수집
csv_files = glob.glob("screening_results_*.csv")
date_pattern = re.compile(r"screening_results_(\d{8})\.csv")
valid_files = []
for f in csv_files:
    match = date_pattern.search(f)
    if match:
        valid_files.append((match.group(1), f))
valid_files.sort()

# 3. 180점 이상 종목 수집
screened_records = []
for date_str, file_path in valid_files:
    try:
        df_screen = pd.read_csv(file_path, dtype={"티커": str, "Code": str})
        ticker_col = next((c for c in ["티커", "ticker", "Code", "code"] if c in df_screen.columns), None)
        score_col = next((c for c in ["총점", "score", "Score", "total_score"] if c in df_screen.columns), None)
        name_col = next((c for c in ["종목명", "name", "Name"] if c in df_screen.columns), None)

        if not ticker_col or not score_col:
            continue
            
        df_high_score = df_screen[df_screen[score_col] >= 180.0]
        
        for idx, row in df_high_score.iterrows():
            ticker = str(row[ticker_col]).zfill(6)
            name = row[name_col] if name_col in df_screen.columns else "Unknown"
            score = row[score_col]
            screened_records.append({
                "screen_date": date_str,
                "ticker": ticker,
                "name": name,
                "score": score
            })
    except Exception as e:
        print(f"Error reading {file_path}: {e}")

print(f"Total screened records (>= 180 score): {len(screened_records)}")

# 4. 수익률 분석 수행
results_A = []  # T+1 매수 시나리오
results_B = []  # T 매수 시나리오

# 누락된 주가 데이터를 FDR로 가져오는 헬퍼 함수
fetched_fdr_data = {}

def get_price_df(ticker):
    # 캐시에서 우선 확인
    if ticker in tickers_data:
        df = tickers_data[ticker].get("df")
        if df is not None and not df.empty:
            # 컬럼명이 소문자일 수 있으므로 표준화
            df = df.copy()
            df.columns = [c.lower() for c in df.columns]
            return df
            
    alt_ticker = "A" + ticker
    if alt_ticker in tickers_data:
        df = tickers_data[alt_ticker].get("df")
        if df is not None and not df.empty:
            df = df.copy()
            df.columns = [c.lower() for c in df.columns]
            return df
            
    # FDR로 받아오기 (메모리 캐시 적용)
    if ticker in fetched_fdr_data:
        return fetched_fdr_data[ticker]
        
    print(f"Fetching {ticker} from FinanceDataReader...")
    try:
        # 넉넉한 범위로 조회
        df = fdr.DataReader(ticker, "2026-03-01", "2026-06-20")
        if df is not None and not df.empty:
            # FDR 컬럼명은 대문자로 시작하는 경우가 많음: Open, High, Low, Close, Volume
            # 이를 소문자 open, high, low, close, volume으로 변경
            df = df.copy()
            df.columns = [c.lower() for c in df.columns]
            fetched_fdr_data[ticker] = df
            time.sleep(0.1) # 과도한 API 요청 방지
            return df
    except Exception as e:
        print(f"Failed to fetch {ticker} from FDR: {e}")
        
    fetched_fdr_data[ticker] = None
    return None

for rec in screened_records:
    ticker = rec["ticker"]
    name = rec["name"]
    date_str = rec["screen_date"]
    
    df_price = get_price_df(ticker)
    if df_price is None or df_price.empty:
        print(f"No price data available for {ticker} ({name}). Skipping.")
        continue
        
    t_date = pd.to_datetime(date_str, format="%Y%m%d")
    
    # 영업일 보정
    if t_date not in df_price.index:
        past_dates = df_price.index[df_price.index <= t_date]
        if len(past_dates) == 0:
            print(f"No valid trading day on or before {date_str} for {ticker} ({name}).")
            continue
        actual_t_date = past_dates[-1]
    else:
        actual_t_date = t_date

    # T일 데이터
    row_T = df_price.loc[actual_t_date]
    open_T = row_T["open"]
    high_T = row_T["high"]
    
    # T일 매수 (B)
    if open_T > 0:
        max_return_B = (high_T - open_T) / open_T * 100
        is_success_B = max_return_B >= 3.0
        results_B.append({
            "screen_date": date_str,
            "actual_T_date": actual_t_date.strftime("%Y-%m-%d"),
            "ticker": ticker,
            "name": name,
            "max_return": max_return_B,
            "success": is_success_B
        })
    
    # T+1일 매수 (A)
    future_dates = df_price.index[df_price.index > actual_t_date]
    if len(future_dates) > 0:
        next_date = future_dates[0]
        row_next = df_price.loc[next_date]
        open_next = row_next["open"]
        high_next = row_next["high"]
        
        if open_next > 0:
            max_return_A = (high_next - open_next) / open_next * 100
            is_success_A = max_return_A >= 3.0
            results_A.append({
                "screen_date": date_str,
                "actual_T_date": actual_t_date.strftime("%Y-%m-%d"),
                "trade_date": next_date.strftime("%Y-%m-%d"),
                "ticker": ticker,
                "name": name,
                "max_return": max_return_A,
                "success": is_success_A
            })

df_A = pd.DataFrame(results_A)
df_B = pd.DataFrame(results_B)

# 요약 결과 출력
print("\n" + "="*50)
print("=== 보완된 백테스트 결과 요약 ===")
print(f"총 스크리닝 진행 일수: {len(valid_files)}일")
print(f"총 스크리닝 점수 180점 이상 종목 검출 건수: {len(screened_records)}건")
print("-"*50)

if not df_A.empty:
    total_A = len(df_A)
    success_A = df_A["success"].sum()
    fail_A = total_A - success_A
    success_rate_A = (success_A / total_A) * 100
    avg_return_A = df_A['max_return'].mean()
    
    print("[시나리오 A] T+1일(다음 영업일) 시초가 진입 -> 당일 최고가 청산")
    print(f" - 분석 대상 건수: {total_A}건")
    print(f" - 성공 건수 (+3% 이상): {success_A}건")
    print(f" - 실패 건수 (+3% 미만): {fail_A}건")
    print(f" - 성공 확률 (승률): {success_rate_A:.2f}%")
    print(f" - 최고 수익률 평균: {avg_return_A:.2f}%")
    print(f" - 최고 수익률 최댓값: {df_A['max_return'].max():.2f}%")
    print(f" - 최고 수익률 최솟값: {df_A['max_return'].min():.2f}%")
else:
    print("[시나리오 A] 분석할 데이터가 없습니다.")

print("-"*50)

if not df_B.empty:
    total_B = len(df_B)
    success_B = df_B["success"].sum()
    fail_B = total_B - success_B
    success_rate_B = (success_B / total_B) * 100
    avg_return_B = df_B['max_return'].mean()
    
    print("[시나리오 B] T일(스크리닝 당일) 시초가 진입 -> 당일 최고가 청산 (미래참조 오류 포함)")
    print(f" - 분석 대상 건수: {total_B}건")
    print(f" - 성공 건수 (+3% 이상): {success_B}건")
    print(f" - 실패 건수 (+3% 미만): {fail_B}건")
    print(f" - 성공 확률 (승률): {success_rate_B:.2f}%")
    print(f" - 최고 수익률 평균: {avg_return_B:.2f}%")
    print(f" - 최고 수익률 최댓값: {df_B['max_return'].max():.2f}%")
    print(f" - 최고 수익률 최솟값: {df_B['max_return'].min():.2f}%")
else:
    print("[시나리오 B] 분석할 데이터가 없습니다.")
    
# 날짜별 성공 여부 요약 표출
print("-"*50)
print("[날짜별 요약 (시나리오 A - 다음 영업일 매수)]")
if not df_A.empty:
    summary_by_date = df_A.groupby("screen_date").agg(
        total_stocks=("ticker", "count"),
        success_stocks=("success", "sum"),
    )
    summary_by_date["success_rate(%)"] = (summary_by_date["success_stocks"] / summary_by_date["total_stocks"]) * 100
    print(summary_by_date.to_string())
