# 쿠팡 재고 대시보드 - 자동 업데이트 설정 가이드

## 🚀 설치 및 설정

### 1. 필수 라이브러리 설치

```bash
cd backend
pip install -r requirements.txt
```

### 2. 환경변수 설정

`.env` 파일을 열어서 쿠팡 로그인 정보를 입력하세요:

```bash
# .env 파일 수정
COUPANG_USER_ID=실제_쿠팡_아이디
COUPANG_USER_PW=실제_쿠팡_비밀번호

# 스케줄러 설정 (기본값: 매일 오전 9시 15분)
AUTO_UPDATE_ENABLED=true
AUTO_UPDATE_HOUR=9
AUTO_UPDATE_MINUTE=15
```

### 3. 서버 실행

```bash
python main.py
```

또는

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## ⏰ 자동 업데이트 기능

### 작동 방식

- 서버가 실행되면 **APScheduler**가 자동으로 시작됩니다
- 매일 지정된 시간(기본: 오전 9시 15분)에 자동으로 데이터를 수집합니다
- 수집 데이터:
  1. 재고 데이터 (광고 대시보드)
  2. 입고 데이터 (입고상세내역)
  3. 정산내역 데이터 (공제금액계정, 당일 월만 업데이트)

### 수집된 데이터 저장 위치

```
backend/
  └── data/
      ├── stock_data.json        # 재고 데이터
      ├── receiving_data.json    # 입고 데이터
      ├── deduction_data.json    # 정산내역 데이터
      └── update_info.json       # 업데이트 정보
```

## 🔧 API 엔드포인트

### 자동 업데이트 상태 조회

```bash
GET http://localhost:8000/api/auto-update/status
```

**응답 예시:**
```json
{
  "success": true,
  "data": {
    "last_run": "2025-02-09T09:15:00",
    "last_success": "2025-02-09T09:20:00",
    "stock_count": 42,
    "receiving_count": 15,
    "deduction_count": 320,
    "errors": []
  }
}
```

### 수동으로 즉시 업데이트 실행

```bash
POST http://localhost:8000/api/auto-update/trigger
```

**응답:**
```json
{
  "success": true,
  "message": "자동 업데이트가 백그라운드에서 실행 중입니다."
}
```

## 📝 스케줄 변경 방법

`.env` 파일에서 시간을 변경하세요:

```bash
# 매일 오후 2시 30분으로 변경
AUTO_UPDATE_HOUR=14
AUTO_UPDATE_MINUTE=30
```

서버를 재시작하면 새로운 스케줄이 적용됩니다.

## 🛑 자동 업데이트 비활성화

자동 업데이트를 사용하지 않으려면:

```bash
AUTO_UPDATE_ENABLED=false
```

## ⚠️ 주의사항

1. **보안**: `.env` 파일에는 민감한 정보가 포함되어 있으므로 절대 공유하지 마세요
2. **서버 실행**: 자동 업데이트가 작동하려면 서버가 계속 실행되어야 합니다
3. **브라우저**: Selenium이 Chrome을 자동으로 실행하므로 서버가 실행 중인 머신에 Chrome이 설치되어 있어야 합니다
4. **로그**: 터미널에서 업데이트 진행 상황을 실시간으로 확인할 수 있습니다

## 🧪 테스트

수동으로 즉시 업데이트를 실행하여 테스트:

```bash
python scheduler.py
```

## 🔄 서버를 백그라운드에서 실행하기 (선택사항)

### macOS/Linux - screen 사용

```bash
# screen 세션 시작
screen -S coupang_api

# 서버 실행
python main.py

# Ctrl+A, D를 눌러 세션에서 분리 (서버는 백그라운드에서 계속 실행)

# 나중에 다시 연결
screen -r coupang_api

# 세션 종료
screen -X -S coupang_api quit
```

### PM2 사용 (Node.js 필요)

```bash
# PM2 설치
npm install -g pm2

# 서버 시작
pm2 start "python main.py" --name coupang-api

# 상태 확인
pm2 status

# 로그 확인
pm2 logs coupang-api

# 중지
pm2 stop coupang-api

# 재시작
pm2 restart coupang-api
```

## 📊 프론트엔드에서 자동 수집 데이터 사용

프론트엔드에서 자동으로 수집된 데이터를 불러오려면 별도의 API를 추가하거나, 기존 API가 data/ 폴더의 캐시된 데이터를 반환하도록 수정할 수 있습니다.

예시: 캐시된 재고 데이터 조회 API 추가 (main.py에):

```python
@app.get("/api/cached-stock")
async def get_cached_stock():
    """자동 수집된 재고 데이터 조회"""
    from scheduler import load_data_from_file
    data = load_data_from_file("stock_data.json")
    if data:
        return data
    else:
        return {"success": False, "error": "캐시된 데이터가 없습니다"}
```
