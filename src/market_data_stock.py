import requests
import json
import time
from datetime import datetime
import pandas as pd
from typing import Optional
from .config import KIS_APP_KEY, KIS_APP_SECRET, KIS_URL_BASE, KIS_ACCOUNT_NO

class KISClient:
    def __init__(self):
        self.app_key = KIS_APP_KEY
        self.app_secret = KIS_APP_SECRET
        self.base_url = KIS_URL_BASE
        self.access_token = self._get_access_token()

    def _get_access_token(self) -> str:
        if not self.app_key or not self.app_secret:
            print("KIS API keys are not fully configured.")
            return ""
            
        url = f"{self.base_url}/oauth2/tokenP"
        headers = {"content-type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        try:
            res = requests.post(url, headers=headers, data=json.dumps(body))
            if res.status_code == 200:
                return res.json().get("access_token", "")
            else:
                print(f"Failed to get KIS token: {res.text}")
                return ""
        except Exception as e:
            print(f"Request error when fetching KIS token: {e}")
            return ""

    def get_daily_ohlcv(self, ticker: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """
        국내주식기간별시세(일/주/월/년) - FHKST03010100
        start_date, end_date format: YYYYMMDD
        """
        if not self.access_token:
            return None

        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST03010100"
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J", # 주식, ETF, ETN
            "FID_INPUT_ISCD": ticker,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": "D", # D: 일, W: 주, M: 월
            "FID_ORG_ADJ_PRC": "0" # 수정주가: 0(수정주가), 1(원주가)
        }
        
        try:
            res = requests.get(url, headers=headers, params=params)
            if res.status_code == 200:
                data = res.json()
                output = data.get("output2", []) # output1 is header, output2 is list of daily ticks
                if not output:
                    return None
                
                df = pd.DataFrame(output)
                # KIS returns data in reverse chronological order
                df = df.iloc[::-1].reset_index(drop=True)
                
                # Format to match OHLCV standard
                df = df.rename(columns={
                    "stck_bsop_date": "date",
                    "stck_oprc": "open",
                    "stck_hgpr": "high",
                    "stck_lwpr": "low",
                    "stck_clpr": "close",
                    "acml_vol": "volume",
                    "acml_tr_pbmn": "value"
                })
                
                # Convert types
                numeric_cols = ["open", "high", "low", "close", "volume", "value"]
                for col in numeric_cols:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col])
                        
                df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
                df.set_index("date", inplace=True)
                
                return df
            else:
                print(f"Error fetching KIS data: {res.text}")
                return None
        except Exception as e:
            print(f"Error: {e}")
            return None

    def get_current_price(self, ticker: str) -> Optional[dict]:
        """
        국내주식 주식현재가 시세 - FHKST01010100
        실시간 현재가, 누적 거래량 등 단건 조회
        """
        if not self.access_token:
            return None
            
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010100"
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker
        }
        
        try:
            res = requests.get(url, headers=headers, params=params)
            if res.status_code == 200:
                data = res.json()
                output = data.get("output", {})
                if not output:
                    return None
                    
                return {
                    "price": int(output.get("stck_prpr", 0)),
                    "volume": int(output.get("acml_vol", 0)),
                    "high": int(output.get("stck_hgpr", 0)),
                    "low": int(output.get("stck_lwpr", 0)),
                    "value": int(output.get("acml_tr_pbmn", 0))
                }
            return None
        except Exception:
            return None

    def get_current_prices_batch(self, tickers: list) -> dict:
        """
        주어진 티커 리스트의 실시간 가격 정보를 반환
        API 호출 빈도(초당 20회)를 고려해 time.sleep 포함
        """
        results = {}
        for i, ticker in enumerate(tickers):
            data = self.get_current_price(ticker)
            if data:
                results[ticker] = data
            if (i + 1) % 15 == 0:
                time.sleep(1.0)
            else:
                time.sleep(0.04)
        return results
