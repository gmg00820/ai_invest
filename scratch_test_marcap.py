import FinanceDataReader as fdr
import pandas as pd

kospi = fdr.StockListing("KOSPI")
print(kospi.columns)
if 'Marcap' in kospi.columns:
    print(kospi[['Code', 'Name', 'Marcap']].head())
