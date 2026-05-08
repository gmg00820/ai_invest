import pickle
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from src.strategy_screener import run_longterm_magic_strategy

cache_file = "market_data_cache_20260422.pkl"
if os.path.exists(cache_file):
    with open(cache_file, "rb") as f:
        tickers_data = pickle.load(f)
    print(f"Loaded {len(tickers_data)} stocks from cache.")
    
    res = run_longterm_magic_strategy(tickers_data)
    print("Strategy Output:")
    print(res)
else:
    print("Cache file not found.")
