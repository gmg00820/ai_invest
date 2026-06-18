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
    try:
        with open(cache_file, "rb") as f:
            tickers_data = pickle.load(f)
    except Exception as e:
        pass

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
        pass

fetched_fdr_data = {}

def get_price_df(ticker):
    if ticker in tickers_data:
        df = tickers_data[ticker].get("df")
        if df is not None and not df.empty:
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
            
    if ticker in fetched_fdr_data:
        return fetched_fdr_data[ticker]
        
    try:
        df = fdr.DataReader(ticker, "2026-03-01", "2026-06-20")
        if df is not None and not df.empty:
            df = df.copy()
            df.columns = [c.lower() for c in df.columns]
            fetched_fdr_data[ticker] = df
            time.sleep(0.05)
            return df
    except Exception:
        pass
    fetched_fdr_data[ticker] = None
    return None

# 데이터를 리스트로 취합
trade_data_list = []

for rec in screened_records:
    ticker = rec["ticker"]
    name = rec["name"]
    date_str = rec["screen_date"]
    
    df_price = get_price_df(ticker)
    if df_price is None or df_price.empty:
        continue
        
    t_date = pd.to_datetime(date_str, format="%Y%m%d")
    
    if t_date not in df_price.index:
        past_dates = df_price.index[df_price.index <= t_date]
        if len(past_dates) == 0:
            continue
        actual_t_date = past_dates[-1]
    else:
        actual_t_date = t_date

    # T일 종가
    close_T = df_price.loc[actual_t_date, "close"]

    # T+1 영업일 데이터 확보
    future_dates = df_price.index[df_price.index > actual_t_date]
    if len(future_dates) > 0:
        next_date = future_dates[0]
        row_next = df_price.loc[next_date]
        open_next = row_next["open"]
        high_next = row_next["high"]
        low_next = row_next["low"]
        close_next = row_next["close"]
        
        if open_next > 0 and close_T > 0:
            trade_data_list.append({
                "screen_date": date_str,
                "ticker": ticker,
                "name": name,
                "close_T": close_T,
                "open": open_next,
                "high": high_next,
                "low": low_next,
                "close": close_next
            })

# 전략 시뮬레이션 함수 (갭 필터 추가)
def simulate_strategy_v2(target_profit_pct, stop_loss_pct=None, max_gap_pct=5.0, min_gap_pct=-1.0):
    returns = []
    skipped_count = 0
    success_count = 0
    loss_count = 0
    
    for trade in trade_data_list:
        op = trade["open"]
        hi = trade["high"]
        lo = trade["low"]
        cl = trade["close"]
        close_T = trade["close_T"]
        
        # 갭 계산 (%)
        gap_pct = (op - close_T) / close_T * 100
        
        # 갭 상승 제한 조건 걸기
        if max_gap_pct is not None and gap_pct > max_gap_pct:
            skipped_count += 1
            continue
        if min_gap_pct is not None and gap_pct < min_gap_pct:
            skipped_count += 1
            continue
            
        max_up = (hi - op) / op * 100
        max_down = (lo - op) / op * 100
        close_ret = (cl - op) / op * 100
        
        is_stop_loss_triggered = False
        if stop_loss_pct is not None and max_down <= stop_loss_pct:
            is_stop_loss_triggered = True
            
        is_target_triggered = max_up >= target_profit_pct
        
        if is_stop_loss_triggered and is_target_triggered:
            final_return = stop_loss_pct
            loss_count += 1
        elif is_stop_loss_triggered:
            final_return = stop_loss_pct
            loss_count += 1
        elif is_target_triggered:
            final_return = target_profit_pct
            success_count += 1
        else:
            final_return = close_ret
            if close_ret > 0:
                success_count += 1
            else:
                loss_count += 1
                
        returns.append(final_return)
        
    total_traded = len(returns)
    if total_traded == 0:
        return None
        
    avg_return = np.mean(returns)
    simple_sum_return = np.sum(returns)
    win_rate = (sum(1 for r in returns if r >= target_profit_pct) / total_traded) * 100
    
    return {
        "target_profit": target_profit_pct,
        "stop_loss": stop_loss_pct,
        "max_gap": max_gap_pct,
        "min_gap": min_gap_pct,
        "total_traded": total_traded,
        "skipped": skipped_count,
        "win_rate": win_rate,
        "avg_return": avg_return,
        "simple_sum_return": simple_sum_return
    }

print("=== 갭 필터(Gap Filter) 추가 시뮬레이션 결과 ===")
print(f"전체 후보 거래 수: {len(trade_data_list)}")
print("-" * 65)

# 갭 상한 필터 테스트 (시초가 갭이 너무 과하게 뜨면 진입 제외)
# 목표 익절 +3%, 손절 없음 (종가 청산) 기준
for max_gap in [1.0, 2.0, 3.0, 4.0, 5.0, 10.0, None]:
    res = simulate_strategy_v2(target_profit_pct=3.0, stop_loss_pct=None, max_gap_pct=max_gap, min_gap_pct=-1.0)
    if res:
        gap_str = f"{max_gap:+.1f}%" if max_gap is not None else "제한없음"
        print(f"갭상한: {gap_str:8s} | 진입거래: {res['total_traded']}건 (필터링:{res['skipped']}건) | 목표달성률: {res['win_rate']:.2f}% | 평균수익: {res['avg_return']:.2f}% | 단리누적: {res['simple_sum_return']:.2f}%")

print("-" * 65)

# 갭 필터 + 손익 구조 개선 그리드 서치
best_simple_sum = -9999
best_params = {}

for target in [1.5, 2.0, 2.5, 3.0, 4.0]:
    for sl in [-1.5, -2.0, -2.5, -3.0, None]:
        for max_gap in [1.0, 2.0, 3.0, 4.0, 5.0, None]:
            res = simulate_strategy_v2(target_profit_pct=target, stop_loss_pct=sl, max_gap_pct=max_gap, min_gap_pct=-1.0)
            if res and res['simple_sum_return'] > best_simple_sum:
                best_simple_sum = res['simple_sum_return']
                best_params = {
                    "target": target,
                    "sl": sl,
                    "max_gap": max_gap,
                    "res": res
                }

print("[최적 갭 필터 전략 조합 발견]")
sl_opt_str = f"{best_params['sl']:+.1f}%" if best_params['sl'] is not None else "종가청산"
gap_opt_str = f"{best_params['max_gap']:+.1f}%" if best_params['max_gap'] is not None else "제한없음"
print(f" -> 최적 목표익절: {best_params['target']:+.1f}%")
print(f" -> 최적 손절기준: {sl_opt_str}")
print(f" -> 최적 갭상한선: {gap_opt_str}")
print(f" -> 실제 진입거래: {best_params['res']['total_traded']}건")
print(f" -> 목표달성률(승률): {best_params['res']['win_rate']:.2f}%")
print(f" -> 거래 평균수익률: {best_params['res']['avg_return']:.2f}%")
print(f" -> 전체 단리누적수익률: {best_params['res']['simple_sum_return']:.2f}%")
