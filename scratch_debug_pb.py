import pickle
import os
import sys
import pandas as pd
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from src.strategy_screener import sma

def debug_pb(tickers_data):
    fail_counts = {
        "len": 0,
        "uptrend": 0,
        "strength": 0,
        "liquidity": 0,
        "score": 0,
        "passed": 0
    }
    
    for ticker, data in tickers_data.items():
        df = data.get('df')
        if df is None or len(df) < 125:
            fail_counts["len"] += 1
            continue
            
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']
        current_close = close.iloc[-1]
        
        # 0. Uptrend
        ma20 = sma(close, length=20)
        ma60 = sma(close, length=60)
        ma120 = sma(close, length=120)
        
        if pd.isna(ma60.iloc[-1]) or pd.isna(ma120.iloc[-1]) or pd.isna(ma20.iloc[-1]):
            fail_counts["uptrend"] += 1
            continue
            
        if ma20.iloc[-1] <= ma60.iloc[-1] and ma60.iloc[-1] <= ma120.iloc[-1]:
            fail_counts["uptrend"] += 1
            continue
            
        # 1. Strength
        recent_high_30 = high.rolling(30).max().iloc[-1]
        recent_low_30 = low.rolling(30).min().iloc[-1]
        
        if pd.isna(recent_high_30) or recent_low_30 == 0:
            fail_counts["strength"] += 1
            continue
            
        rise_pct = (recent_high_30 - recent_low_30) / recent_low_30
        score_strength = min(20.0, rise_pct * 40.0)
        
        # 2. Pullback
        pullback_depth = (current_close - recent_high_30) / recent_high_30
        if -0.25 <= pullback_depth <= -0.05:
            if -0.20 <= pullback_depth <= -0.07:
                score_depth = 15.0
            else:
                score_depth = 7.0
        else:
            score_depth = 0.0
            
        ma20_val = ma20.iloc[-1]
        ma60_val = ma60.iloc[-1]
        prox_ma20 = abs(current_close - ma20_val) / ma20_val if ma20_val > 0 else 1.0
        prox_ma60 = abs(current_close - ma60_val) / ma60_val if ma60_val > 0 else 1.0
        best_prox = min(prox_ma20, prox_ma60)
        
        if best_prox <= 0.03:
            score_prox = 20.0
        elif best_prox <= 0.08:
            score_prox = 20.0 - ((best_prox - 0.03) / 0.05) * 10.0
        elif best_prox <= 0.15:
            score_prox = 10.0 - ((best_prox - 0.08) / 0.07) * 10.0
        else:
            score_prox = 0.0
            
        score_pullback = score_depth + score_prox
        
        # 3. Vol
        vol_ma3 = volume.rolling(3).mean().iloc[-1]
        vol_ma20 = volume.rolling(20).mean().iloc[-1]
        if pd.isna(vol_ma3) or vol_ma20 == 0:
            score_vol = 0.0
        else:
            vol_ratio = vol_ma3 / vol_ma20
            if vol_ratio <= 0.5:
                score_vol = 30.0
            elif vol_ratio <= 1.0:
                score_vol = 30.0 * (1.0 - vol_ratio) * 2.0
            else:
                score_vol = 0.0
                
        # 4. NR7
        daily_ranges = high - low
        recent_7d_ranges = daily_ranges.tail(7)
        score_nr7 = 0.0
        if len(recent_7d_ranges) == 7:
            current_range = recent_7d_ranges.iloc[-1]
            min_range = recent_7d_ranges.min()
            if current_range == min_range and current_range > 0:
                score_nr7 = 15.0
                
        total_score = score_strength + score_pullback + score_vol + score_nr7
        
        marcap = data.get('marcap', 0)
        if marcap > 0:
            if marcap < 50_000_000_000:
                fail_counts["liquidity"] += 1
                continue
        else:
            if 'value' in df.columns:
                val_ma20 = sma(df['value'], length=20).iloc[-1]
            else:
                val_ma20 = (close * volume).rolling(20, min_periods=5).mean().iloc[-1]
            if pd.isna(val_ma20) or val_ma20 <= 10_000_000: 
                fail_counts["liquidity"] += 1
                continue
                
        if total_score < 15.0:
            fail_counts["score"] += 1
            continue
            
        fail_counts["passed"] += 1

    print(fail_counts)

today_str = pd.Timestamp.now().strftime("%Y%m%d")
cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"market_data_cache_{today_str}.pkl")
with open(cache_file, "rb") as f:
    tickers_data = pickle.load(f)
debug_pb(tickers_data)
