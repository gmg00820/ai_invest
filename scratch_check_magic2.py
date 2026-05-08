import pickle
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from src.strategy_screener import run_longterm_magic_strategy

cache_file = "market_data_cache_20260427.pkl"
if os.path.exists(cache_file):
    with open(cache_file, "rb") as f:
        tickers_data = pickle.load(f)
    print(f"Loaded {len(tickers_data)} stocks from cache.")
    
    # Just to trace scoring, I'll print the first 5 stocks with score > 0
    res = run_longterm_magic_strategy(tickers_data)
    print("Strategy Output:")
    print(res)
else:
    print("Cache file not found.")
