import os
import glob
import re
import pickle
import pandas as pd
import numpy as np
import FinanceDataReader as fdr
import time
import sys
import json

# 현재 디렉토리 모듈 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.screener import StockScreener
from src.strategy_screener import (
    run_mean_reversion,
    run_volatility_breakout,
    run_multi_factor,
    run_longterm_magic_strategy,
    run_pullback_breakout_strategy
)

# 1. 설정 로드
SETTINGS_FILE = "screener_settings.json"
settings = {}
if os.path.exists(SETTINGS_FILE):
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except:
        pass

surge_limit = settings.get("surge_limit", 45)
w_vol = settings.get("w_vol", 30)
w_trend = settings.get("w_trend", 20)
w_tech = settings.get("w_tech", 20)
w_wave = settings.get("w_wave", 20)
w_fund = settings.get("w_fund", 20)
use_news = settings.get("use_news", False)
w_news = settings.get("w_news", 10)

print("--- Screener Weights Config ---")
print(f"surge_limit: {surge_limit}")
print(f"w_vol: {w_vol}, w_trend: {w_trend}, w_tech: {w_tech}, w_wave: {w_wave}, w_fund: {w_fund}")
print(f"use_news: {use_news}, w_news: {w_news}")
print("--------------------------------")

# 2. market_data_cache_*.pkl 파일 목록 수집 (날짜 역순 정렬해서 뒤에서 T+1 주가 조회 가능하도록 함)
cache_files = glob.glob("market_data_cache_*.pkl")
date_pattern = re.compile(r"market_data_cache_(\d{8})\.pkl")
valid_caches = []
for f in cache_files:
    match = date_pattern.search(f)
    if match:
        valid_caches.append((match.group(1), f))
valid_caches.sort() # 날짜 오름차순 정렬

# 3. 최신 캐시 로드 (T+1일 주가 정보 참고용)
latest_cache_file = "market_data_cache_20260615.pkl"
price_reference_data = {}
if os.path.exists(latest_cache_file):
    print(f"Loading reference cache {latest_cache_file} for T+1 pricing...")
    with open(latest_cache_file, "rb") as f:
        price_reference_data = pickle.load(f)
else:
    print("WARNING: Latest cache not found, will rely on FDR API for all pricing.")

# FDR API 호출 메모리 캐시
fetched_fdr_data = {}

def get_price_df(ticker):
    if ticker in price_reference_data:
        df = price_reference_data[ticker].get("df")
        if df is not None and not df.empty:
            df = df.copy()
            df.columns = [c.lower() for c in df.columns]
            return df
    alt_ticker = "A" + ticker
    if alt_ticker in price_reference_data:
        df = price_reference_data[alt_ticker].get("df")
        if df is not None and not df.empty:
            df = df.copy()
            df.columns = [c.lower() for c in df.columns]
            return df
            
    if ticker in fetched_fdr_data:
        return fetched_fdr_data[ticker]
        
    # FDR fetch
    try:
        df = fdr.DataReader(ticker, "2026-03-01", "2026-06-25")
        if df is not None and not df.empty:
            df = df.copy()
            df.columns = [c.lower() for c in df.columns]
            fetched_fdr_data[ticker] = df
            time.sleep(0.05)
            return df
    except Exception as e:
        pass
    fetched_fdr_data[ticker] = None
    return None

def get_next_day_price(ticker, actual_t_date):
    df = get_price_df(ticker)
    if df is None or df.empty:
        return None
        
    actual_t_date_dt = pd.to_datetime(actual_t_date)
    df.index = pd.to_datetime(df.index)
    
    # actual_t_date 이후의 첫 번째 영업일
    future_dates = df.index[df.index > actual_t_date_dt]
    if len(future_dates) > 0:
        next_date = future_dates[0]
        row_next = df.loc[next_date]
        if float(row_next["open"]) > 0:
            return {
                "date": next_date.strftime("%Y-%m-%d"),
                "open": float(row_next["open"]),
                "high": float(row_next["high"]),
                "low": float(row_next["low"]),
                "close": float(row_next["close"])
            }
    return None

# 백테스트 실행
results = []

print(f"Starting backtest across {len(valid_caches)} cache files...")

for date_str, cache_path in valid_caches:
    t_date = pd.to_datetime(date_str, format="%Y%m%d")
    print(f"Processing date: {date_str}")
    
    try:
        with open(cache_path, "rb") as f:
            tickers_data = pickle.load(f)
    except Exception as e:
        print(f"Failed to load cache {cache_path}: {e}")
        continue
        
    # Screener 객체 초기화 및 가중치 적용
    screener = StockScreener()
    if len(screener.conditions) >= 7:
        screener.conditions[0].max_surge_rate = surge_limit
        screener.conditions[1].weight = w_vol
        screener.conditions[2].weight = w_trend
        screener.conditions[3].weight = w_tech
        screener.conditions[4].weight = w_wave
        screener.conditions[5].weight = w_fund
        screener.conditions[6].weight = w_news if use_news else 0
        screener.conditions[6].is_active = use_news

    # 6가지 퀀트 알고리즘 계산
    try:
        results_df = screener.run(tickers_data)
        mr_df = run_mean_reversion(tickers_data)
        vb_df = run_volatility_breakout(tickers_data)
        mf_df = run_multi_factor(tickers_data)
        magic_df = run_longterm_magic_strategy(tickers_data)
        pb_df = run_pullback_breakout_strategy(tickers_data)
    except Exception as e:
        print(f"Failed to run strategies for date {date_str}: {e}")
        continue

    def get_top_tickers_with_scores(df, score_col):
        if df is None or df.empty or score_col not in df.columns: 
            return {}
        df_top = df.head(30)
        return dict(zip(df_top['티커'], df_top[score_col]))

    scores_base = get_top_tickers_with_scores(results_df, '총점')
    scores_mr = get_top_tickers_with_scores(mr_df, '스코어')
    scores_vb = get_top_tickers_with_scores(vb_df, '스코어')
    scores_mf = get_top_tickers_with_scores(mf_df, '스코어')
    scores_magic = get_top_tickers_with_scores(magic_df, '스코어')
    scores_pb = get_top_tickers_with_scores(pb_df, '스코어')
    
    all_tickers = set(scores_base.keys()) | set(scores_mr.keys()) | set(scores_vb.keys()) | set(scores_mf.keys()) | set(scores_magic.keys()) | set(scores_pb.keys())
    
    # overlap_df 구성
    overlap_data = []
    for t in all_tickers:
        combo = []
        total_score = 0.0
        
        if t in scores_base: 
            combo.append("기본스윙")
            total_score += scores_base[t]
        if t in scores_mr: 
            combo.append("과매도반전")
            total_score += scores_mr[t]
        if t in scores_vb: 
            combo.append("변동성돌파")
            total_score += scores_vb[t]
        if t in scores_mf: 
            combo.append("멀티팩터")
            total_score += scores_mf[t]
        if t in scores_magic:
            combo.append("롱텀매직")
            total_score += scores_magic[t]
        if t in scores_pb:
            combo.append("눌림목")
            total_score += scores_pb[t]
            
        if len(combo) >= 2:
            name = ""
            for df_source in [results_df, mr_df, vb_df, mf_df, magic_df, pb_df]:
                if df_source is not None and not df_source.empty and t in df_source['티커'].values:
                    name = df_source.loc[df_source['티커'] == t, '종목명'].iloc[0]
                    break
            overlap_data.append({
                "티커": t,
                "종목명": name,
                "합산 스코어": total_score,
                "조합": " + ".join(combo)
            })
            
    if not overlap_data:
        continue
        
    overlap_df = pd.DataFrame(overlap_data)
    target_overlap = overlap_df[overlap_df["합산 스코어"] >= 200]
    
    for idx, row in target_overlap.iterrows():
        ticker = row["티커"]
        name = row["종목명"]
        combo = row["조합"]
        total_score = row["합산 스코어"]
        
        basic_score = 0.0
        if not results_df.empty and ticker in results_df["티커"].values:
            basic_score = results_df.loc[results_df["티커"] == ticker, "총점"].iloc[0]
            
        if basic_score < 180.0:
            continue
            
        # T+1일 주가 정보 조회
        price_info = get_next_day_price(ticker, t_date)
        if price_info is None:
            continue
            
        open_price = price_info["open"]
        high_price = price_info["high"]
        
        max_return = (high_price - open_price) / open_price * 100
        success = max_return >= 3.0
        
        results.append({
            "screen_date": date_str,
            "trade_date": price_info["date"],
            "ticker": ticker,
            "name": name,
            "basic_score": basic_score,
            "overlap_score": total_score,
            "combo": combo,
            "open": open_price,
            "high": high_price,
            "max_return": max_return,
            "success": success
        })
        print(f"  [MATCH] {date_str} {name}({ticker}) | Swing: {basic_score:.1f}, Overlap: {total_score:.1f} | T+1: {price_info['date']} Open: {open_price:,.0f} -> High: {high_price:,.0f} | Return: {max_return:.2f}% | Success: {success}")

# 결과 출력
print("\n" + "="*80)
print("=== 골든크로스(>=200) + 기본스크리닝(>=180) 교집합 백테스트 결과 ===")
print("="*80)

if not results:
    print("조건을 만족하는 종목이 전혀 발견되지 않았거나 가격 정보가 부족합니다.")
else:
    df_res = pd.DataFrame(results)
    total_trades = len(df_res)
    success_trades = df_res["success"].sum()
    fail_trades = total_trades - success_trades
    win_rate = (success_trades / total_trades) * 100
    avg_return = df_res["max_return"].mean()
    
    print(f"총 분석 영업일수: {len(valid_caches)}일")
    print(f"총 진입 거래 건수: {total_trades}건")
    print(f"성공 건수 (+3% 이상): {success_trades}건")
    print(f"실패 건수 (+3% 미만): {fail_trades}건")
    print(f"성공 확률 (승률): {win_rate:.2f}%")
    print(f"최고 수익률 평균: {avg_return:.2f}%")
    print(f"최고 수익률 최댓값: {df_res['max_return'].max():.2f}%")
    print(f"최고 수익률 최솟값: {df_res['max_return'].min():.2f}%")
    
    print("-"*80)
    print("세부 거래 기록:")
    sorted_df = df_res.sort_values(by="screen_date")
    for idx, r in sorted_df.iterrows():
        print(f"[{r['screen_date']} -> {r['trade_date']}] {r['name']}({r['ticker']}) | 스윙: {r['basic_score']:.1f} | 합산: {r['overlap_score']:.1f} | 수익률: {r['max_return']:.2f}% | {'성공' if r['success'] else '실패'}")
        
    print("-"*80)
    df_res.to_csv("intersection_backtest_results.csv", index=False, encoding="utf-8-sig")
    print("Saved results to intersection_backtest_results.csv")
