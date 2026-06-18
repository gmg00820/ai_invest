# 1. Base Image 설정 (Streamlit 및 데이터 분석 라이브러리에 적합한 Python slim 이미지 사용)
FROM python:3.10-slim

# 2. 환경 변수 설정
# PYTHONUNBUFFERED: 로그가 버퍼링 없이 즉시 출력되도록 설정
# PYTHONDONTWRITEBYTECODE: pyc 파일 생성을 방지하여 컨테이너 용량 최적화
# STREAMLIT_SERVER_ENABLE_CORS / ENABLE_XSRF_PROTECTION: 외부 터널(ngrok, Cloudflare)이나 프록시를 통해 접속할 때 WebSocket 연결 오류 방지
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_ENABLE_CORS=false \
    STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false

# 3. 작업 디렉토리 설정
WORKDIR /app

# 4. 필수 시스템 패키지 설치 (의존성 패키지 빌드용 및 헬스체크용 curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 5. 의존성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. 소스 코드 복사 (.dockerignore에 지정된 파일은 제외됨)
COPY . .

# 7. Streamlit 기본 포트 노출
EXPOSE 8501

# 8. 컨테이너 실행 명령 정의
CMD ["streamlit", "run", "app.py"]
