import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import sys
import os
import time
import pickle
import FinanceDataReader as fdr
import plotly.graph_objects as go
import json
import requests

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from src.screener import StockScreener
from src.market_data_stock import KISClient
from src.strategy_screener import run_mean_reversion, run_volatility_breakout, run_multi_factor, run_split_strategy

st.set_page_config(page_title="주식 스크리닝 대시보드", page_icon="📈", layout="wide")

st.title("📈 퀀트 주식 스크리닝 대시보드")
st.markdown("최근 급등한 종목은 제외하고, 상승 초입에 있는 유망 종목을 다양한 조건식으로 발굴합니다.")

# ==========================================
# 설정 저장/불러오기 기능
# ==========================================
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screener_settings.json")
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

s = load_settings()

if "surge_limit" not in st.session_state: st.session_state.surge_limit = s.get("surge_limit", 45)
if "w_vol" not in st.session_state: st.session_state.w_vol = s.get("w_vol", 30)
if "w_trend" not in st.session_state: st.session_state.w_trend = s.get("w_trend", 20)
if "w_tech" not in st.session_state: st.session_state.w_tech = s.get("w_tech", 20)
if "w_wave" not in st.session_state: st.session_state.w_wave = s.get("w_wave", 20)
if "w_fund" not in st.session_state: st.session_state.w_fund = s.get("w_fund", 20)
if "use_news" not in st.session_state: st.session_state.use_news = s.get("use_news", False)
if "w_news" not in st.session_state: st.session_state.w_news = s.get("w_news", 10)
if "top_n" not in st.session_state: st.session_state.top_n = s.get("top_n", 20)

st.sidebar.header("🕹️ 구동 모드 선택")
app_mode = st.sidebar.radio(
    "어떤 분석을 진행할까요?",
    options=["1. 장마감 정규 스크리닝", "2. 실시간 주도주 모니터링", "3. AI 주식 애널리스트 분석"],
    index=0
)
st.sidebar.markdown("---")

# Sidebar Settings
st.sidebar.header("⚙️ 스크리닝 조건 설정")

st.sidebar.slider("급등 제외 기준 (최근 3일 상승률 %)", min_value=10, max_value=100, step=5, key="surge_limit")
st.sidebar.markdown("---")

st.sidebar.slider("📊 거래 조건 가중치", 0, 100, step=5, key="w_vol")
st.sidebar.slider("📈 추세 조건 가중치 (MA20)", 0, 100, step=5, key="w_trend")
st.sidebar.slider("🛠 기술적 지표 가중치 (Env/MACD)", 0, 100, step=5, key="w_tech")
st.sidebar.slider("🌊 엘리어트 파동 가중치", 0, 100, step=5, key="w_wave")
st.sidebar.slider("💼 재무/가치 지표 가중치 (ROE/PER)", 0, 100, step=5, key="w_fund")
st.sidebar.checkbox("📰 네이버 뉴스 언급량 분석 사용", key="use_news")
if st.session_state.use_news:
    st.sidebar.slider("📰 뉴스 언급량 가중치", 0, 100, step=5, key="w_news")

st.sidebar.markdown("---")
st.sidebar.number_input("조회할 상위 종목 개수", min_value=5, max_value=100, key="top_n")

if st.sidebar.button("💾 현재 설정(가중치) 저장하기"):
    new_settings = {
        "surge_limit": st.session_state.surge_limit,
        "w_vol": st.session_state.w_vol,
        "w_trend": st.session_state.w_trend,
        "w_tech": st.session_state.w_tech,
        "w_wave": st.session_state.w_wave,
        "w_fund": st.session_state.w_fund,
        "use_news": st.session_state.use_news,
        "w_news": st.session_state.w_news,
        "top_n": st.session_state.top_n
    }
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(new_settings, f, ensure_ascii=False, indent=4)
    st.sidebar.success("✅ 설정이 파일에 안전하게 저장되었습니다!")
    time.sleep(1)

st.sidebar.markdown("---")
if st.sidebar.button("🗑 오늘 수집된 캐시 삭제 (데이터 강제 재수집)"):
    today_str_tmp = datetime.now().strftime("%Y%m%d")
    cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"market_data_cache_{today_str_tmp}.pkl")
    if os.path.exists(cache_path):
        os.remove(cache_path)
    if "tickers_data" in st.session_state:
        del st.session_state["tickers_data"]
    st.sidebar.success("캐시가 완전히 삭제되었습니다! 다음 스크리닝 시 데이터를 처음부터 다시 수집합니다.")
    time.sleep(1.5)
    st.rerun()

@st.cache_data(ttl=3600*24)
def fetch_market_tickers():
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tickers_master.csv")
    try:
        kospi = fdr.StockListing("KOSPI")
        kosdaq = fdr.StockListing("KOSDAQ")
        all_stocks = pd.concat([kospi, kosdaq])
        
        # 테마(업종) 매핑을 위해 KRX-DESC 수집
        desc = fdr.StockListing("KRX-DESC")
        if not desc.empty and 'Sector' in desc.columns:
            sector_map = dict(zip(desc['Code'], desc['Sector']))
            all_stocks['Theme'] = all_stocks['Code'].map(sector_map).fillna("기타")
        else:
            all_stocks['Theme'] = "기타"
            
        # 성공 시(로컬 환경), 백그라운드에서 최신 종목을 CSV로 덮어씌워 자동 저장합니다.
        try:
            all_stocks.to_csv(csv_path, index=False, encoding="utf-8-sig")
        except:
            pass
            
        return all_stocks
    except Exception as e:
        # 실패 시(클라우드 환경), 로컬에서 자동 저장해둔 CSV 파이프라인으로 전환하여 데이터를 공급합니다!
        try:
            if os.path.exists(csv_path):
                return pd.read_csv(csv_path, dtype={"Code": str})
        except:
            pass
        return pd.DataFrame()

@st.cache_data(ttl=3600*12)
def fetch_market_fundamentals():
    pkl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fundamentals_master.pkl")
    try:
        from pykrx import stock
        # pykrx의 조회일자를 생략하면 가장 최근 영업일 기준 데이터를 가져옵니다.
        kospi = stock.get_market_fundamental(market="KOSPI")
        kosdaq = stock.get_market_fundamental(market="KOSDAQ")
        all_funds = pd.concat([kospi, kosdaq])
        
        # 성공 시(로컬 환경), 백그라운드에서 최신 재무데이터를 PKL로 자동 저장합니다.
        try:
            import pickle
            with open(pkl_path, "wb") as f:
                pickle.dump(all_funds, f)
        except:
            pass
            
        return all_funds
    except Exception as e:
        # 에러 시(해외 클라우드 차단 또는 모듈 미설치), 로컬에서 자동 저장해둔 PKL을 불러옵니다.
        try:
            import pickle
            if os.path.exists(pkl_path):
                with open(pkl_path, "rb") as f:
                    return pickle.load(f)
        except:
            pass
        return pd.DataFrame()

# API 클라이언트는 1번만 생성하여 토큰 발급 횟수 초과(EGW00133) 에러를 방지합니다.
@st.cache_resource
def get_kis_client():
    return KISClient()

if app_mode == "2. 실시간 주도주 모니터링":
    st.subheader("🔥 실시간 주도주 모니터링 (Top 100 단독 모드)")
    st.markdown("전체 스크리닝 데이터를 받는 3분의 기다림 없이, **현재 시장에서 거래대금이 가장 많이 터지는 시장 주도주 Top 100 종목**만 단숨에 추려 독립적인 실시간 감시를 시작합니다.")
    
    if st.button("🚀 실시간 감시 준비 및 시작", type="primary"):
        import copy
        
        rt_placeholder = st.empty()
        
        with rt_placeholder.container():
            st.info("🔄 당일 전 종목 거래대금 순위 스캔 중... (1초 소요)")
            
            try:
                # pykrx의 잦은 에러 및 속도 저하를 막기 위해 안정적인 FinanceDataReader(FDR) 사용
                krx_df = fdr.StockListing('KRX')
                
                # 'Amount'(거래대금) 기준으로 정렬하기 위해 수치형 변환
                krx_df['Amount'] = pd.to_numeric(krx_df['Amount'], errors='coerce').fillna(0)
                
                # 거래가 활발한 코스피/코스닥 위주로 필터링 (코넥스 제외)
                krx_df = krx_df[~krx_df['Market'].str.contains("KONEX", na=False)]
                
                # 거래대금 상위 100종목 추출
                top_100_df = krx_df.sort_values("Amount", ascending=False).head(100)
                top_100_tickers = top_100_df['Code'].tolist()
                
                check_date = datetime.now()
                today_str = check_date.strftime("%Y%m%d")
            except Exception as e:
                st.error(f"거래대금 순위 조회를 위한 기초 데이터 수집에 실패했습니다: {e}")
                st.stop()
            
            st.info("✅ 1차 유동성 필터링 완료! Top 100 종목 과거 데이터만 초고속 수집 중... (약 4초 소요)")
            
            kis_client = get_kis_client()
            all_stocks = fetch_market_tickers()
            if all_stocks.empty:
                st.error("한국거래소(KRX) 통신 오류로 종목 정보를 불러올 수 없습니다. 시스템 점검 시간이거나 서버(해외 IP) 환경에서 접속이 차단되었을 수 있습니다.")
                st.stop()
            ticker_to_name = dict(zip(all_stocks['Code'], all_stocks['Name']))
            ticker_to_theme = dict(zip(all_stocks['Code'], all_stocks['Theme']))
            
            start_date = (check_date - timedelta(days=150)).strftime("%Y%m%d")
            
            rt_tickers_data = {}
            fund_df = fetch_market_fundamentals()
            
            for ticker in top_100_tickers:
                try:
                    df = kis_client.get_daily_ohlcv(ticker, start_date, today_str)
                    if df is not None and not df.empty:
                        try:
                            fund_row = fund_df.loc[ticker].to_dict() if (not fund_df.empty and ticker in fund_df.index) else {}
                        except:
                            fund_row = {}
                            
                        rt_tickers_data[ticker] = {
                            "name": ticker_to_name.get(ticker, ticker),
                            "theme": ticker_to_theme.get(ticker, "기타"),
                            "df": df,
                            "fundamentals": fund_row
                        }
                except:
                    pass
                time.sleep(0.04)
        
        st.success(f"🔥 실시간 추적을 시작합니다! (기준일: {today_str}) - 중지하려면 새로고침(F5)을 누르세요.")
        
        screener = StockScreener()
        screener.conditions[0].max_surge_rate = st.session_state.surge_limit
        screener.conditions[1].weight = st.session_state.w_vol
        screener.conditions[2].weight = st.session_state.w_trend
        screener.conditions[3].weight = st.session_state.w_tech
        screener.conditions[4].weight = st.session_state.w_wave
        screener.conditions[5].weight = st.session_state.w_fund
        screener.conditions[6].weight = st.session_state.w_news if st.session_state.use_news else 0
        screener.conditions[6].is_active = st.session_state.use_news
        
        def get_top_tickers_with_scores(df, score_col):
            if df.empty or score_col not in df.columns: return {}
            df_top = df.head(30)
            return dict(zip(df_top['티커'], df_top[score_col]))
            
        while True:
            current_prices = kis_client.get_current_prices_batch(top_100_tickers)
            
            rt_tickers_data_copy = copy.deepcopy(rt_tickers_data)
            
            for t, price_data in current_prices.items():
                if t in rt_tickers_data_copy:
                    df = rt_tickers_data_copy[t]['df']
                    if df is not None and not df.empty:
                        df.iloc[-1, df.columns.get_loc('close')] = price_data['price']
                        df.iloc[-1, df.columns.get_loc('volume')] = price_data['volume']
                        df.iloc[-1, df.columns.get_loc('high')] = max(df['high'].iloc[-1], price_data['high'])
                        df.iloc[-1, df.columns.get_loc('low')] = min(df['low'].iloc[-1], price_data['low'])
                        if 'value' in df.columns: # 거래대금 업데이트 (주의: 당일 실시간이므로 근사치일 수 있음)
                            df.iloc[-1, df.columns.get_loc('value')] = price_data['value']
            
            rt_results_df = screener.run(rt_tickers_data_copy)
            rt_mr_df = run_mean_reversion(rt_tickers_data_copy)
            rt_vb_df = run_volatility_breakout(rt_tickers_data_copy)
            rt_mf_df = run_multi_factor(rt_tickers_data_copy)
            rt_split_df = run_split_strategy(rt_tickers_data_copy)
            
            rt_scores_base = get_top_tickers_with_scores(rt_results_df, '총점')
            rt_scores_mr = get_top_tickers_with_scores(rt_mr_df, '스코어')
            rt_scores_vb = get_top_tickers_with_scores(rt_vb_df, '스코어')
            rt_scores_mf = get_top_tickers_with_scores(rt_mf_df, '스코어')
            rt_scores_split = get_top_tickers_with_scores(rt_split_df, '스코어')
            
            rt_all_tickers = set(rt_scores_base.keys()) | set(rt_scores_mr.keys()) | set(rt_scores_vb.keys()) | set(rt_scores_mf.keys()) | set(rt_scores_split.keys())
            rt_overlap_data = []
            
            for t in rt_all_tickers:
                combo = []
                total_score = 0.0
                
                if t in rt_scores_base: 
                    combo.append("기본스윙")
                    total_score += rt_scores_base[t]
                if t in rt_scores_mr: 
                    combo.append("과매도반전")
                    total_score += rt_scores_mr[t]
                if t in rt_scores_vb: 
                    combo.append("변동성돌파")
                    total_score += rt_scores_vb[t]
                if t in rt_scores_mf: 
                    combo.append("멀티팩터")
                    total_score += rt_scores_mf[t]
                if t in rt_scores_split:
                    combo.append("스플릿전용")
                    total_score += rt_scores_split[t]
                
                if combo:
                    name = rt_tickers_data_copy[t]['name']
                    theme = rt_tickers_data_copy[t].get('theme', '기타')
                    rt_overlap_data.append({
                        "종목명": name,
                        "티커": t,
                        "테마(업종)": theme,
                        "통과 개수": len(combo),
                        "합산 스코어": round(total_score, 1),
                        "조합 (교집합)": " + ".join(combo),
                        "현재가": current_prices.get(t, {}).get('price', 0)
                    })
            
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with rt_placeholder.container():
                st.caption(f"🔄 마지막 시세 갱신: {now_str} (약 6~10초 주기 자동 갱신 중)")
                if rt_overlap_data:
                    rt_overlap_df = pd.DataFrame(rt_overlap_data)
                    rt_overlap_df = rt_overlap_df.sort_values(by=["통과 개수", "합산 스코어"], ascending=[False, False]).reset_index(drop=True)
                    st.dataframe(
                        rt_overlap_df, 
                        use_container_width=True, 
                        hide_index=True,
                        column_config={
                            "테마(업종)": st.column_config.TextColumn("테마(업종)", width="medium"),
                            "통과 개수": st.column_config.ProgressColumn("조건 통과 레이더", min_value=1, max_value=5, format="★ %d개"),
                            "합산 스코어": st.column_config.NumberColumn("합산 스코어", format="%.1f 점"),
                            "현재가": st.column_config.NumberColumn("실시간 현재가", format="%d 원")
                        }
                    )
                else:
                    st.warning("현재 포착된 종목이 없습니다.")
            
            time.sleep(2)

    st.stop() # 모드 2일 경우 여기서 전체 스트림릿 사이클을 끝냄. 모드 1 로직을 실행하지 않음.

elif app_mode == "3. AI 주식 애널리스트 분석":
    st.subheader("🤖 AI 주식 애널리스트 & 퀀트 트레이더")
    st.markdown("기관투자자 수준의 퀀트 분석과 매매 타이밍을 추론합니다. 종목명을 입력해주세요.")
    
    # helper for env
    def get_env_var(key):
        import streamlit as st
        import os
        try:
            # 로컬에서 불필요한 'No secrets files found' 경고가 뜨지 않도록 파일 존재 여부 우선 확인
            if os.path.exists(os.path.join(os.getcwd(), ".streamlit", "secrets.toml")):
                if key in st.secrets:
                    return st.secrets[key]
        except Exception:
            pass
        try:
            env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith(f"{key}="):
                        return line.strip().split("=", 1)[1]
        except Exception:
            pass
        return ""
        
    def get_naver_news(query):
        client_id = get_env_var("NAVER_CLIENT_ID")
        client_secret = get_env_var("NAVER_CLIENT_SECRET")
        if not client_id or not client_secret: return []
        url = "https://openapi.naver.com/v1/search/news.json"
        headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
        params = {"query": query, "display": 5, "sort": "date"}
        try:
            res = requests.get(url, headers=headers, params=params)
            if res.status_code == 200:
                import re
                items = res.json().get("items", [])
                clean_items = []
                for item in items:
                    title = re.sub(r'<[^>]*>', '', item['title']).replace('&quot;', '"')
                    desc = re.sub(r'<[^>]*>', '', item['description']).replace('&quot;', '"')
                    clean_items.append(f"[{item['pubDate']}] {title} - {desc}")
                return clean_items
        except:
            pass
        return []

    gemini_key = get_env_var("GEMINI_API_KEY")
    if not gemini_key:
        st.error("GEMINI_API_KEY가 .env 파일에 설정되어 있지 않습니다.")
        st.stop()
        
    with st.form("ai_analyst_form"):
        stock_name = st.text_input("분석할 종목명 (예: 삼성전자)", placeholder="종목명을 입력하세요")
        invest_period = st.radio("투자 기간 지정", options=["단기(1~4주)", "중기(1~3개월)"], horizontal=True)
        submitted = st.form_submit_button("🚀 AI 분석 시작", type="primary")
        
    if submitted:
        if not stock_name:
            st.warning("종목명을 입력해주세요.")
        else:
            with st.spinner(f"'{stock_name}' 종목에 대한 다각도 AI 분석을 진행하고 있습니다... (약 10~20초 소요)"):
                # 1. 뼈대 데이터 가져오기
                all_stocks = fetch_market_tickers()
                if all_stocks.empty:
                    st.error("한국거래소(KRX) 통신 오류로 종목 정보를 불러올 수 없습니다. 시스템 점검 시간이거나 서버 환경(해외 클라우드)에서 접속이 차단되었을 수 있습니다.")
                    st.stop()
                    
                if stock_name not in all_stocks['Name'].values:
                    st.error(f"'{stock_name}' 종목을 찾을 수 없습니다. 정확한 종목명을 입력해주세요.")
                else:
                    ticker = all_stocks[all_stocks['Name'] == stock_name]['Code'].iloc[0]
                    theme = all_stocks[all_stocks['Code'] == ticker]['Theme'].iloc[0] if 'Theme' in all_stocks.columns else '알수없음'
                    kis_client = get_kis_client()
                    current_price_data = kis_client.get_current_price(ticker)
                    current_price = current_price_data.get('price', '알수없음') if current_price_data else '알수없음'
                    
                    # 최근 뉴스 가져오기
                    recent_news = get_naver_news(stock_name)
                    news_text = "\n".join(recent_news) if recent_news else "최근 뉴스 데이터를 불러오지 못했습니다."
                    
                    # 재무 데이터
                    fund_df = fetch_market_fundamentals()
                    try:
                        fund_row = fund_df.loc[ticker] if (not fund_df.empty and ticker in fund_df.index) else None
                        if fund_row is not None:
                            per = fund_row.get('PER', 'N/A')
                            pbr = fund_row.get('PBR', 'N/A')
                            roe = fund_row.get('ROE', 'N/A')
                            eps = fund_row.get('EPS', 'N/A')
                            bps = fund_row.get('BPS', 'N/A')
                            fund_text = f"PER: {per}, PBR: {pbr}, ROE: {roe}, EPS: {eps}, BPS: {bps}"
                        else:
                            fund_text = "재무 데이터를 불러오지 못했습니다."
                    except:
                        fund_text = "재무 데이터를 불러오지 못했습니다."
                        
                    # 가격 및 거래량 추이
                    today_str = datetime.now().strftime("%Y%m%d")
                    start_str = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d")
                    df_hist = kis_client.get_daily_ohlcv(ticker, start_str, today_str)
                    hist_text = ""
                    if df_hist is not None and not df_hist.empty:
                        recent_5 = df_hist.tail(5)
                        avg_vol = df_hist['volume'].tail(20).mean()
                        hist_text = f"최근 20일 평균 거래량: {avg_vol:,.0f}주\n최근 5일 종가 추이: {recent_5['close'].tolist()}"
                    
                    # 프롬프트 구성
                    system_prompt = '''너는 기관투자자 수준의 주식 애널리스트이자 퀀트 트레이더다.
목표는 단순 정보 요약이 아니라,
"매수 / 매도 타이밍"을 도출하는 것이다.

다음 4가지 분석을 반드시 수행한다:
1. 리포트(증권사/애널리스트 의견)
2. 공시(전자공시, 기업 이벤트)
3. 실적(재무/성장성/이익 추세)
4. 수급 및 기술적 흐름

모든 분석은 "타이밍 판단"을 위한 근거로 사용한다.

절대 금지:
- 근거 없는 낙관/비관
- 단순 뉴스 요약
- 애매한 표현 (예: "좋아 보인다", "지켜볼 필요 있음")

반드시 확률 기반 판단을 내려라.'''

                    user_prompt = f'''
[분석 대상]
- 종목명: {stock_name} (테마/업종: {theme})
- 현재가: {current_price}원
- 투자 기간: {invest_period}

[실시간 파악 팩트트랙(참고용)]
- 최근 실적/재무 지표: {fund_text}
- 최근 기업 뉴스:
{news_text}
- 최근 과거 5일 가격 및 수급:
{hist_text}

[요청]
아래 항목을 기반으로 매수/매도 타이밍을 도출하라.

📌 분석 로직 (순서대로 진행)
1️⃣ 리포트 분석 (목표주가 대비 괴리율, 핵심 투자포인트, 최근 톤 변화 추정)
2️⃣ 공시 분석 (최근 이벤트, 호재/악재 분류, 주가 선반영 판단)
3️⃣ 실적 분석 (위 실적 지표 기반)
4️⃣ 수급 분석 (위 과거 가격 및 거래량 기반)
5️⃣ 기술적 분석 (현재 위치, 지지/저항선 추정)
6️⃣ 종합 판단 (현재 위치 정의: 초기 상승/추세 중간/과열/하락 추세)
7️⃣ 매매 전략 도출

📌 출력 포맷 (매우 중요, 아래 형태 유지)
[핵심 요약]
- 현재 상태: (한 줄)
- 결론: 매수 / 관망 / 매도

[근거 요약]
- 리포트:
- 공시:
- 실적:
- 수급:

[타이밍 전략]
- 매수 타이밍:
- 추가 매수 구간:
- 매도 타이밍:
- 손절 라인:

[확률 기반 판단]
- 상승 확률: XX%
- 하락 확률: XX%

[리스크]
- 주요 하락 트리거 3가지
'''
                    # API 호출
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={gemini_key}"
                    headers = {"Content-Type": "application/json"}
                    payload = {
                        "contents": [
                            {"role": "user", "parts": [{"text": system_prompt + "\n\n" + user_prompt}]}
                        ],
                        "generationConfig": {
                            "temperature": 0.2
                        }
                    }
                    try:
                        import urllib3
                        urllib3.disable_warnings() 
                        resp = requests.post(url, headers=headers, json=payload, verify=False)
                        if resp.status_code == 200:
                            result_text = resp.json()['candidates'][0]['content']['parts'][0]['text']
                            st.success("분석이 완료되었습니다!")
                            st.markdown("---")
                            st.markdown(result_text)
                        elif resp.status_code == 404:
                            st.error(f"Gemini API 모델 오류 (404): {resp.text}")
                        else:
                            st.error(f"Gemini API 호출 오류: {resp.status_code}")
                            st.text(resp.text)
                    except Exception as e:
                        st.error(f"오류가 발생했습니다: {e}")
                        
    st.stop()

# ================================
# 모드 1: 장마감 정규 스크리닝 (전 종목)
# ================================

if "app_screening_started" not in st.session_state:
    st.session_state.app_screening_started = False

def start_screening_callback():
    st.session_state.app_screening_started = True

st.button("🚀 정규 스크리닝 시작 / 전체 데이터 수집 (약 3분 소요)", type="primary", on_click=start_screening_callback)

if st.session_state.app_screening_started:
    all_stocks = fetch_market_tickers()
    if all_stocks.empty:
        st.stop()
        
    all_tickers = all_stocks['Code'].tolist()
    ticker_to_name = dict(zip(all_stocks['Code'], all_stocks['Name']))
    ticker_to_theme = dict(zip(all_stocks['Code'], all_stocks['Theme']))
    
    today = datetime.now()
    today_str = today.strftime("%Y%m%d")
    start_date = (today - timedelta(days=150)).strftime("%Y%m%d")
    
    # 1. 스크리너 설정 (Session State 값 반영)
    screener = StockScreener()
    screener.conditions[0].max_surge_rate = st.session_state.surge_limit
    screener.conditions[1].weight = st.session_state.w_vol
    screener.conditions[2].weight = st.session_state.w_trend
    screener.conditions[3].weight = st.session_state.w_tech
    screener.conditions[4].weight = st.session_state.w_wave
    screener.conditions[5].weight = st.session_state.w_fund
    screener.conditions[6].weight = st.session_state.w_news if st.session_state.use_news else 0
    screener.conditions[6].is_active = st.session_state.use_news
    
    # 세션 상태(Session State)를 활용하여 한 번 다운로드 받은 데이터는 재사용 (API 호출 절약 및 속도 극대화)
    if "tickers_data" not in st.session_state or st.session_state.get("last_fetch_date") != today_str:
        
        CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"market_data_cache_{today_str}.pkl")
        
        # 1. 파일 캐시가 있으면 3분 걸리는 API 다운로드를 패스하고 즉시 불러옵니다! (브라우저나 서버를 재시작해도 유지됨)
        cache_is_valid = False
        if os.path.exists(CACHE_FILE):
            status_text = st.empty()
            status_text.info(f"💾 오늘의 시세 데이터 캐시 파일({os.path.basename(CACHE_FILE)})을 불러오는 중입니다...")
            try:
                with open(CACHE_FILE, "rb") as f:
                    cached_data = pickle.load(f)
                
                # 비정상 종료로 인해 저장된 종목이 비정상적으로 적다면(ex. 1000개 미만) 무효화
                if len(cached_data) > 1000:
                    tickers_data = cached_data
                    cache_is_valid = True
                    status_text.success(f"✅ 로컬 캐시에서 총 {len(tickers_data)}개 종목 데이터를 1초만에 불러왔습니다! (API 호출 생략)")
                    time.sleep(1)
                    status_text.empty()
                    
                    st.session_state["tickers_data"] = tickers_data
                    st.session_state["last_fetch_date"] = today_str
                else:
                    status_text.warning("⚠️ 저장된 캐시 데이터가 불완전합니다. 다시 수집합니다...")
                    time.sleep(1)
                    status_text.empty()
            except Exception as e:
                pass
            
        # 2. 파일 캐시가 없거나 불완전하면 KIS API로 전체 데이터를 받아온 뒤 파일로 영구 저장합니다.
        if not cache_is_valid:
            tickers_data = {}
            client = get_kis_client()
            fund_df = fetch_market_fundamentals()
            
            progress_bar = st.progress(0, text="최초 데이터 수집 중 (오늘은 1회만 약 3분 소요됩니다)...")
            total = len(all_tickers)
            
            for i, ticker in enumerate(all_tickers):
                if i % 30 == 0: # UI 업데이트
                    progress_bar.progress(i / total, text=f"데이터 수집 중... ({i}/{total})")
                    
                try:
                    df = client.get_daily_ohlcv(ticker, start_date, today_str)
                    if df is not None and not df.empty:
                        # 해당 종목의 재무 데이터 조회
                        try:
                            fund_row = fund_df.loc[ticker].to_dict() if (not fund_df.empty and ticker in fund_df.index) else {}
                        except:
                            fund_row = {}
                            
                        tickers_data[ticker] = {
                            "name": ticker_to_name.get(ticker, ticker),
                            "theme": ticker_to_theme.get(ticker, "기타"),
                            "df": df,
                            "fundamentals": fund_row
                        }
                except:
                    pass
                time.sleep(0.04) # KIS API 초당 20건 제한 보호
                
            # 캐시 파일 쓰기
            with open(CACHE_FILE, "wb") as f:
                pickle.dump(tickers_data, f)
                
            st.session_state["tickers_data"] = tickers_data
            st.session_state["last_fetch_date"] = today_str
            progress_bar.progress(1.0, text="✅ 오늘 치 데이터 수집 및 캐시 저장 완료!")
            time.sleep(1) # 완료 메시지 보여주기용
            progress_bar.empty()
    else:
        tickers_data = st.session_state["tickers_data"]
        st.success("세션에 저장된 데이터를 불러옵니다. (0초 만에 조건 재평가 완료)")
    
    # 1. 스크리너 설정 (Sidebar 값 반영)
    screener = StockScreener()
    # SurgeExcludeCondition은 index 0이라 가정
    screener.conditions[0].max_surge_rate = st.session_state.surge_limit
    screener.conditions[1].weight = st.session_state.w_vol
    screener.conditions[2].weight = st.session_state.w_trend
    screener.conditions[3].weight = st.session_state.w_tech
    screener.conditions[4].weight = st.session_state.w_wave
    screener.conditions[5].weight = st.session_state.w_fund
    screener.conditions[6].weight = st.session_state.w_news if st.session_state.use_news else 0
    screener.conditions[6].is_active = st.session_state.use_news
    
    # 2. 분석 실행 (모든 전략 동시 처리)
    current_params = (
        st.session_state.surge_limit, st.session_state.w_vol, st.session_state.w_trend,
        st.session_state.w_tech, st.session_state.w_wave, st.session_state.w_fund,
        st.session_state.w_news if st.session_state.use_news else 0,
        st.session_state.get("last_fetch_date")
    )
    
    if "cached_dfs" not in st.session_state or st.session_state.get("last_algo_params") != current_params:
        with st.spinner("5가지 핵심 퀀트 알고리즘으로 전 종목을 분석 및 스코어링 중입니다... (최초 1회만 소요)"):
            results_df = screener.run(tickers_data)
            mr_df = run_mean_reversion(tickers_data)
            vb_df = run_volatility_breakout(tickers_data)
            mf_df = run_multi_factor(tickers_data)
            split_df = run_split_strategy(tickers_data)
            
            st.session_state.cached_dfs = {
                "results": results_df, "mr": mr_df, "vb": vb_df, "mf": mf_df, "split": split_df
            }
            st.session_state.last_algo_params = current_params
    else:
        # 캐시된 결과 즉시 반환
        cached = st.session_state.cached_dfs
        results_df, mr_df, vb_df, mf_df, split_df = cached["results"], cached["mr"], cached["vb"], cached["mf"], cached["split"]
        
    # === 교집합 분석 및 추천 ===
    def get_top_tickers_with_scores(df, score_col):
        if df.empty or score_col not in df.columns: 
            return {}
        df_top = df.head(30)
        return dict(zip(df_top['티커'], df_top[score_col]))

    scores_base = get_top_tickers_with_scores(results_df, '총점')
    scores_mr = get_top_tickers_with_scores(mr_df, '스코어')
    scores_vb = get_top_tickers_with_scores(vb_df, '스코어')
    scores_mf = get_top_tickers_with_scores(mf_df, '스코어')
    scores_split = get_top_tickers_with_scores(split_df, '스코어')
    
    all_tickers = set(scores_base.keys()) | set(scores_mr.keys()) | set(scores_vb.keys()) | set(scores_mf.keys()) | set(scores_split.keys())
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
        if t in scores_split:
            combo.append("스플릿전용")
            total_score += scores_split[t]
        
        if len(combo) >= 2:
            advice = ""
            if "기본스윙" in combo and "멀티팩터" in combo:
                advice = "🔥 안심 매수: 우량 실적주의 안정적인 우상향 초기 (가장 추천하는 중장기 스윙)"
            elif "변동성돌파" in combo and "멀티팩터" in combo:
                advice = "🚀 돌파 매매: 우량주에 수급이 몰리며 대시세 분출 시도 중 (시장 주도주)"
            elif "과매도반전" in combo and "멀티팩터" in combo:
                advice = "💎 줍줍 기회: 펀더멘탈 우량주가 비이성적으로 폭락함 (강력한 가치투자 매수 타이밍)"
            elif "기본스윙" in combo and "변동성돌파" in combo:
                advice = "🌊 단기 모멘텀: 추세 호조 상태에서 단기 수급이 터진 상황 (짧은 손절선 잡고 단기 트레이딩)"
            else:
                advice = "⚠️ 강력한 다중 신호 포착. 특이한 복합 시그널이므로 분할 매수 접근."

            name = ""
            for df_source in [results_df, mr_df, vb_df, mf_df, split_df]:
                if not df_source.empty and t in df_source['티커'].values:
                    name = df_source.loc[df_source['티커'] == t, '종목명'].iloc[0]
                    break
                    
            overlap_data.append({
                "종목명": name,
                "티커": t,
                "합산 스코어": round(total_score, 1),
                "조합 (교집합)": " + ".join(combo),
                "대응 전략 가이드": advice
            })
            
    if overlap_data:
        st.markdown("---")
        st.subheader("🏆 골든 크로스: 2개 이상 알고리즘 교집합 추천 종목")
        st.markdown("서로 다른 투자 논리를 가진 두 개 이상의 검색식에 **동시에 포착된 매우 유망한 종목**들입니다. 각 알고리즘에서 얻은 점수를 합산하여 랭킹을 매겼습니다.")
        
        overlap_df = pd.DataFrame(overlap_data)
        # 높은 합산 점수 순으로 내림차순 정렬
        overlap_df = overlap_df.sort_values(by="합산 스코어", ascending=False).reset_index(drop=True)
        
        st.dataframe(
            overlap_df, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "합산 스코어": st.column_config.NumberColumn("합산 스코어", format="%.1f 점"),
                "대응 전략 가이드": st.column_config.TextColumn("대응 전략 가이드", width="large"),
                "조합 (교집합)": st.column_config.TextColumn("조합 (교집합)", width="medium")
            }
        )
        st.markdown("---")
        
    # 전략 탭 생성
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "기존 스크리닝", 
        "전략1: 과매도 & 모멘텀", 
        "전략2: 변동성 돌파", 
        "전략3: 멀티 팩터",
        "전략4: 스플릿 전용"
    ])
    
    with tab1:
        if results_df.empty:
            st.warning("조건을 만족하는 종목이 없습니다. 조건을 완화해 보세요.")
        else:
            st.success(f"조건 통과 종목: 총 {len(results_df)}개 발견!")
            
            # 상위 N개 필터링
            if len(results_df) > st.session_state.top_n:
                final_df = results_df.head(st.session_state.top_n)
                st.info(f"선택하신 상위 {st.session_state.top_n}개 종목만 표시합니다.")
            else:
                final_df = results_df
                
            # 데이터를 스타일링하여 표시
            st.subheader("📊 완벽 통과 종목 목록 (총점 순)")
            
            st.dataframe(
                final_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "종목명": st.column_config.TextColumn("종목명", width="medium"),
                    "티커": st.column_config.TextColumn("티커", width="small"),
                    "테마(업종)": st.column_config.TextColumn("테마(업종)", width="medium"),
                    "총점": st.column_config.ProgressColumn(
                        "총점 (Score)",
                        format="%.1f 점",
                        min_value=0,
                        max_value=120
                    ),
                    "만족조건 (가독성 최적화)": st.column_config.TextColumn("주요 만족 지표 요약", width="large")
                }
            )
            
            # 차트 시각화 섹션
            st.markdown("---")
            st.subheader("📈 통과 종목 캔들차트 상세보기")
            st.caption("클릭하여 각 종목의 150일간 주가 추세 캔들을 확인하세요.")
            
            for idx, row in final_df.iterrows():
                ticker = row['티커']
                name = row['종목명']
                theme = row.get('테마(업종)', '기타')
                score = row['총점']
                
                stock_df = tickers_data[ticker]['df']
                
                with st.expander(f"[{ticker}] {name} (업종: {theme}) - ⭐️ {score:.1f}점"):
                    # 타입 캐스팅 강제로 Plotly 축 스케일 오류(문자열 매핑) 방지
                    fig = go.Figure(data=[go.Candlestick(
                        x=pd.to_datetime(stock_df.index) if type(stock_df.index) != pd.DatetimeIndex else stock_df.index,
                        open=pd.to_numeric(stock_df['open'], errors='coerce'),
                        high=pd.to_numeric(stock_df['high'], errors='coerce'),
                        low=pd.to_numeric(stock_df['low'], errors='coerce'),
                        close=pd.to_numeric(stock_df['close'], errors='coerce'),
                        name=name
                    )])
                    fig.update_layout(
                        title=f"'{name}' 일봉 차트 (최근 150일)",
                        yaxis_title="주가 (KRW)",
                        xaxis_rangeslider_visible=False,
                        height=450,
                        margin=dict(l=0, r=0, t=40, b=0),
                        template="plotly_white"
                    )
                    st.plotly_chart(fig, use_container_width=True)
            
            # CSV 다운로드 버튼
            csv = final_df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 CSV 다운로드",
                data=csv,
                file_name=f"stock_screening_{today_str}.csv",
                mime="text/csv"
            )

    with tab2:
        st.subheader("📉 전략 1: 과매도 & 모멘텀 반전")
        st.markdown("**진입조건**: Z-Score < -2.0 & 최근 RSI(14) < 30 & 60MA/120MA 추세 & 거래량/시가 갭하락 필터 통과")
        
        if mr_df.empty:
            st.warning("현재 장세에서 모든 과매도 반전 조건을 만족하는 종목이 없습니다.")
        else:
            st.success(f"{len(mr_df)}개 종목 발견! (Z-Score 오름차순 정렬)")
            st.dataframe(mr_df, use_container_width=True, hide_index=True)

    with tab3:
        st.subheader("🚀 전략 2: 변동성 돌파 (Volatility Breakout)")
        st.markdown("**진입조건**: 변동성 수축(ATR비율 < 0.7) 후 당일 거래량 급증 + 20일 최고가 돌파")
            
        if vb_df.empty:
            st.warning("현재 장세에서 변동성 돌파 초기 조건을 만족하는 종목이 없습니다.")
        else:
            st.success(f"{len(vb_df)}개 종목 발견! (돌파 강도 내림차순 정렬)")
            st.dataframe(vb_df, use_container_width=True, hide_index=True)

    with tab4:
        st.subheader("⚖️ 전략 3: 멀티 팩터 Z-Score 랭킹")
        st.markdown("**조건**: Value(20%), Quality(32.5%), Momentum(32.5%), Low-Vol(15%) Z-Score 점수 상위 20%")
            
        if mf_df.empty:
            st.warning("분석할 수 있는 종목이 부족합니다.")
        else:
            st.success(f"상위 20%의 멀티팩터 우량 종목 {len(mf_df)}개입니다. (총점 내림차순)")
            st.dataframe(mf_df, use_container_width=True, hide_index=True)

    with tab5:
        st.subheader("♻️ 전략 4: 스플릿 전용 (회복/되돌림)")
        st.markdown("**진입조건**: 뛰어난 유동성(대금/거래량), 재무 건전성(흑자), 높은 변동성(ATR 3~8%, 52주 고저차 50% 이상) + 잦은 테마순환")
            
        if split_df.empty:
            st.warning("현재 장세에서 변동성이 크면서 재무와 유동성이 모두 뒷받침되는 스플릿 전용 종목이 없습니다.")
        else:
            st.success(f"{len(split_df)}개 종목 발견! (스코어 내림차순 정렬)")
            st.dataframe(split_df, use_container_width=True, hide_index=True)

