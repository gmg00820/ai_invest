import os
from dotenv import load_dotenv

load_dotenv()

# Upbit API Keys
UPBIT_ACCESS_KEY = os.getenv("UPBIT_ACCESS_KEY", "")
UPBIT_SECRET_KEY = os.getenv("UPBIT_SECRET_KEY", "")

# Korea Investment & Securities (한국투자증권) API Keys
KIS_APP_KEY = "PSwHw8RAhjkDyTuPHJkgGs101Ax7E9fdoxyw"
KIS_APP_SECRET = "8RPBY2wEdD8Rq1pyI6YOVFWcCZQQmhxNQCXdxpABgnSO0GaoTaiE+rSw7adhIzr7GVc1UJ2SyKEN8Je+yrOs8wU3jXf56jq3eBuzkYAU++GOLDepaeYrAk2+77fmnxMM8muAsXaP03wyhvUx5YZ5Yd+RguB3Hc2NC3tVGG0dtuIrB7nI1j0="
KIS_ACCOUNT_NO = "@2968840"
KIS_URL_BASE = os.getenv("KIS_URL_BASE", "https://openapi.koreainvestment.com:9443") # 실전투자
# KIS_URL_BASE = "https://openapivts.koreainvestment.com:29443" # 모의투자

# Gemini API Key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyCC2hq4sQD4oN230CARbwQWmWJsBxHBuCU")

# Naver API Keys (For News Search)
NAVER_CLIENT_ID = "aK7Ii2sQQwN7XasRm7Xo"
NAVER_CLIENT_SECRET = "8nxzrYsL9_"

