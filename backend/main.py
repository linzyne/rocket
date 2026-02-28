"""
쿠팡 재고 대시보드 API 서버
FastAPI를 사용하여 프론트엔드에 재고 데이터를 제공합니다.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
import atexit

from scraper import fetch_stock_data, fetch_receiving_data, fetch_settlement_data, fetch_deduction_data, fetch_ad_report, fetch_ad_report_only, fetch_supplier_combined
from scheduler import start_scheduler, stop_scheduler, auto_update_all_data, get_last_update_info

# FastAPI 앱 초기화
app = FastAPI(
    title="쿠팡 재고 대시보드 API",
    description="쿠팡 광고 대시보드에서 재고 데이터를 수집하는 API (자동 업데이트 지원)",
    version="1.1.0"
)

# 앱 시작 시 스케줄러 시작
@app.on_event("startup")
async def startup_event():
    """서버 시작 시 스케줄러 시작"""
    start_scheduler()

# 앱 종료 시 스케줄러 중지
@app.on_event("shutdown")
async def shutdown_event():
    """서버 종료 시 스케줄러 중지"""
    stop_scheduler()

# 프로세스 종료 시에도 스케줄러 중지
atexit.register(stop_scheduler)

# CORS 설정 (file:// 프로토콜 지원을 위해 credentials=False + origins=*)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 스레드 풀 (Selenium은 동기 작업이므로 별도 스레드에서 실행)
executor = ThreadPoolExecutor(max_workers=2)


class LoginRequest(BaseModel):
    """로그인 요청 모델"""
    user_id: str
    user_pw: str
    include_ad_report: Optional[bool] = False


class DeductionRequest(BaseModel):
    """공제금액 조회 요청 모델 (스마트 조회 지원)"""
    user_id: str
    user_pw: str
    start_year: Optional[int] = 2025
    start_month: Optional[int] = 11


class StockItem(BaseModel):
    """재고 아이템 모델"""
    product_name: str
    stock: int


class StockResponse(BaseModel):
    """재고 응답 모델"""
    success: bool
    data: Optional[list] = None
    count: Optional[int] = None
    timestamp: Optional[str] = None
    error: Optional[str] = None
    ad_data: Optional[dict] = None
    ad_error: Optional[str] = None


@app.get("/")
async def root():
    """루트 엔드포인트 - API 상태 확인"""
    return {
        "message": "쿠팡 재고 대시보드 API",
        "status": "running",
        "auto_update": "enabled",
        "endpoints": {
            "POST /api/fetch-stock": "재고 데이터 조회",
            "POST /api/fetch-receiving": "입고 데이터 조회",
            "POST /api/fetch-settlement": "정산 데이터 조회",
            "POST /api/fetch-deduction": "공제금액 데이터 조회",
            "GET /api/auto-update/status": "자동 업데이트 상태 조회",
            "POST /api/auto-update/trigger": "수동으로 즉시 업데이트 실행"
        }
    }


@app.post("/api/fetch-stock", response_model=StockResponse)
async def fetch_stock(request: LoginRequest):
    """
    쿠팡 재고 데이터를 조회합니다.
    
    - **user_id**: 쿠팡 로그인 ID
    - **user_pw**: 쿠팡 로그인 비밀번호
    """
    try:
        # Selenium 작업을 별도 스레드에서 실행 (비동기 처리)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            executor,
            fetch_stock_data,
            request.user_id,
            request.user_pw,
            True,  # debug_mode
            request.include_ad_report
        )
        
        if result["success"]:
            # Supabase에 재고 데이터 저장 (날짜별 누적)
            if result.get("data"):
                try:
                    from db import save_data, load_data
                    from datetime import datetime
                    today = datetime.now().strftime('%Y-%m-%d')
                    existing = load_data("stock_history") or {}
                    existing[today] = result["data"]
                    save_data("stock_history", existing)
                    print(f"✅ Supabase에 재고 데이터 저장 완료 ({today}, {len(result['data'])}건)")
                    # 광고 데이터도 함께 왔으면 저장
                    if result.get("ad_data"):
                        from datetime import timedelta
                        ad_existing = load_data("ad_history") or {}
                        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                        ad_existing[yesterday] = result["ad_data"]
                        save_data("ad_history", ad_existing)
                        print(f"✅ Supabase에 광고 데이터 저장 완료 ({yesterday})")
                except Exception as db_err:
                    print(f"⚠️ Supabase 재고 저장 실패: {db_err}")
            return StockResponse(
                success=True,
                data=result["data"],
                count=result["count"],
                timestamp=result["timestamp"],
                ad_data=result.get("ad_data"),
                ad_error=result.get("ad_error")
            )
        else:
            return StockResponse(
                success=False,
                error=result.get("error", "알 수 없는 오류가 발생했습니다.")
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/fetch-receiving")
async def fetch_receiving(request: LoginRequest):
    """
    쿠팡 로켓 supplier에서 오늘의 입고 데이터를 조회합니다.
    
    - **user_id**: 쿠팡 로그인 ID
    - **user_pw**: 쿠팡 로그인 비밀번호
    """
    try:
        # Selenium 작업을 별도 스레드에서 실행 (비동기 처리)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            executor,
            fetch_receiving_data,
            request.user_id,
            request.user_pw
        )
        
        if result["success"]:
            # Supabase에 입고 데이터 저장 (날짜별 누적)
            data_by_date = result.get("data_by_date", {})
            if data_by_date or result.get("data"):
                try:
                    from db import save_data, load_data
                    existing = load_data("receiving_history") or {}
                    if data_by_date:
                        # 날짜별 그룹핑된 데이터 사용
                        for date_str, sku_data in data_by_date.items():
                            existing[date_str] = sku_data
                    else:
                        # 폴백: date 필드 기반 그룹핑
                        from datetime import datetime
                        for item in result["data"]:
                            sku = item.get("sku_name", "")
                            d = item.get("date", datetime.now().strftime('%Y-%m-%d'))
                            if sku:
                                if d not in existing:
                                    existing[d] = {}
                                existing[d][sku] = existing[d].get(sku, 0) + item.get("quantity", 0)
                    save_data("receiving_history", existing)
                    print(f"✅ Supabase에 입고 데이터 저장 완료 ({len(data_by_date or {})}일치)")
                except Exception as db_err:
                    print(f"⚠️ Supabase 입고 저장 실패: {db_err}")
            return {
                "success": True,
                "data": result.get("data", []),
                "data_by_date": data_by_date,
                "count": result.get("count", 0),
                "timestamp": result.get("timestamp"),
                "message": result.get("message", "")
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "알 수 없는 오류가 발생했습니다.")
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/fetch-settlement")
async def fetch_settlement(request: LoginRequest):
    """
    쿠팡 로켓 supplier에서 정산 데이터를 조회합니다.
    SKU명, 총단가, 지급일 정보를 수집합니다.
    
    - **user_id**: 쿠팡 로그인 ID
    - **user_pw**: 쿠팡 로그인 비밀번호
    """
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            executor,
            fetch_settlement_data,
            request.user_id,
            request.user_pw
        )
        
        if result["success"]:
            return {
                "success": True,
                "data": result.get("data", []),
                "count": result.get("count", 0),
                "timestamp": result.get("timestamp"),
                "message": result.get("message", "")
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "알 수 없는 오류가 발생했습니다.")
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/fetch-deduction")
async def fetch_deduction(request: DeductionRequest):
    """
    쿠팡 정산 → 공제금액계정 데이터를 조회합니다.
    스마트 조회: start_year, start_month 지정 시 해당 월부터만 조회
    
    - **user_id**: 쿠팡 로그인 ID
    - **user_pw**: 쿠팡 로그인 비밀번호
    - **start_year**: 조회 시작 연도 (기본: 2025)
    - **start_month**: 조회 시작 월 (기본: 11)
    """
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            executor,
            fetch_deduction_data,
            request.user_id,
            request.user_pw,
            request.start_year,
            request.start_month
        )
        
        if result["success"]:
            # 크롤링 성공 시 Supabase에 자동 저장 (월별 병합)
            if result.get("data"):
                try:
                    from db import save_data, load_data
                    new_data = result["data"]
                    new_months = set(r.get("_query_month", "") for r in new_data if r.get("_query_month"))
                    existing = load_data("deduction_data") or {}
                    old_records = existing.get("data", [])
                    kept = [r for r in old_records if r.get("_query_month", "") not in new_months]
                    merged = kept + new_data
                    save_data("deduction_data", {
                        "success": True,
                        "data": merged,
                        "count": len(merged),
                        "timestamp": result.get("timestamp")
                    })
                    print(f"✅ Supabase 정산 병합 저장 (기존 {len(kept)}건 + 신규 {len(new_data)}건 = {len(merged)}건)")
                except Exception as db_err:
                    print(f"⚠️ Supabase 저장 실패: {db_err}")
            return {
                "success": True,
                "data": result.get("data", []),
                "count": result.get("count", 0),
                "timestamp": result.get("timestamp"),
                "message": result.get("message", "")
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "알 수 없는 오류가 발생했습니다.")
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/cached-deduction")
async def get_cached_deduction():
    """백엔드에 캐시된 정산내역 데이터를 반환합니다."""
    import json
    # 1. Supabase DB에서 로드 시도
    try:
        from db import load_data
        cached = load_data("deduction_data")
        if cached is not None:
            return cached
    except Exception as e:
        print(f"⚠️ DB에서 정산 데이터 로드 실패: {e}")

    # 2. 로컬 파일에서 로드 (폴백)
    data_path = os.path.join(os.path.dirname(__file__), "data", "deduction_data.json")
    try:
        if os.path.exists(data_path):
            with open(data_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            return cached
        else:
            return {"success": False, "data": [], "error": "캐시된 데이터가 없습니다."}
    except Exception as e:
        return {"success": False, "data": [], "error": str(e)}


@app.get("/health")
async def health_check():
    """헬스 체크 엔드포인트"""
    return {"status": "healthy"}


@app.get("/api/auto-update/status")
async def get_auto_update_status():
    """
    자동 업데이트 상태 조회

    Returns:
        - last_run: 마지막 실행 시각
        - last_success: 마지막 성공 시각
        - stock_count: 재고 데이터 개수
        - receiving_count: 입고 데이터 개수
        - deduction_count: 정산내역 데이터 개수
        - errors: 오류 목록
    """
    try:
        info = get_last_update_info()
        return {
            "success": True,
            "data": info
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auto-update/trigger")
async def trigger_auto_update(background_tasks: BackgroundTasks):
    """
    수동으로 자동 업데이트를 즉시 실행합니다.
    백그라운드에서 실행되므로 즉시 응답을 반환합니다.
    """
    try:
        # 백그라운드에서 업데이트 실행
        background_tasks.add_task(auto_update_all_data)
        return {
            "success": True,
            "message": "자동 업데이트가 백그라운드에서 실행 중입니다. 상태는 /api/auto-update/status에서 확인하세요."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



class SupplierRequest(BaseModel):
    """공급자 통합 조회 요청 모델"""
    user_id: str
    user_pw: str
    days_back: Optional[int] = 1
    start_year: Optional[int] = 2025
    start_month: Optional[int] = 11


@app.post("/api/fetch-supplier-all")
async def fetch_supplier_all(request: SupplierRequest):
    """
    supplier.coupang.com에 1회 로그인하여 입고 + 정산 데이터를 한 번에 수집합니다.
    """
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            executor,
            fetch_supplier_combined,
            request.user_id,
            request.user_pw,
            request.days_back,
            request.start_year,
            request.start_month
        )

        receiving = result.get("receiving", {})
        deduction = result.get("deduction", {})

        # 입고 데이터 Supabase 저장
        if receiving.get("success"):
            data_by_date = receiving.get("data_by_date", {})
            if data_by_date:
                try:
                    from db import save_data, load_data
                    existing = load_data("receiving_history") or {}
                    for date_str, sku_data in data_by_date.items():
                        existing[date_str] = sku_data
                    save_data("receiving_history", existing)
                    print(f"✅ Supabase 입고 저장 ({len(data_by_date)}일치)")
                except Exception as db_err:
                    print(f"⚠️ Supabase 입고 저장 실패: {db_err}")

        # 정산 데이터 Supabase 저장 (월별 병합 - 기존 다른 월 데이터 보존)
        if deduction.get("success") and deduction.get("data"):
            try:
                from db import save_data, load_data
                new_data = deduction["data"]
                # 새 데이터에 포함된 월 목록
                new_months = set(r.get("_query_month", "") for r in new_data if r.get("_query_month"))
                # 기존 데이터에서 새 수집 월에 해당하지 않는 레코드 유지
                existing = load_data("deduction_data") or {}
                old_records = existing.get("data", [])
                kept = [r for r in old_records if r.get("_query_month", "") not in new_months]
                merged = kept + new_data
                save_data("deduction_data", {
                    "success": True,
                    "data": merged,
                    "count": len(merged),
                    "timestamp": deduction.get("timestamp")
                })
                print(f"✅ Supabase 정산 병합 저장 (기존 {len(kept)}건 + 신규 {len(new_data)}건 = {len(merged)}건)")
            except Exception as db_err:
                print(f"⚠️ Supabase 정산 저장 실패: {db_err}")

        response_data = {
            "success": True,
            "receiving": receiving,
            "deduction": deduction
        }
        return response_data

    except Exception as e:
        print(f"❌ [API 오류] fetch-supplier-all: {e}", flush=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/fetch-ad-report")
async def fetch_ad(request: SupplierRequest):
    """
    쿠팡 광고 리포트 데이터를 별도로 조회합니다.
    days_back일치 데이터를 수집합니다 (기본: 7일).
    """
    try:
        days_back = request.days_back or 7
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            executor,
            fetch_ad_report_only,
            request.user_id,
            request.user_pw,
            days_back,
            True  # debug_mode
        )

        if result and result["success"]:
            # Supabase에 광고 데이터 저장 (날짜별 대체)
            if result.get("data_by_date"):
                try:
                    from db import save_data, load_data
                    existing = load_data("ad_history") or {}
                    for date_str, ad_data in result["data_by_date"].items():
                        # 기존에 products(상세)가 있고 새 데이터에 없으면 유지
                        old = existing.get(date_str)
                        if old and old.get("products") and not ad_data.get("products"):
                            ad_data["products"] = old["products"]
                        existing[date_str] = ad_data
                    save_data("ad_history", existing)
                    print(f"✅ Supabase에 광고 데이터 저장 완료 ({len(result['data_by_date'])}일치)")
                except Exception as db_err:
                    print(f"⚠️ Supabase 광고 저장 실패: {db_err}")
            return {
                "success": True,
                "data_by_date": result.get("data_by_date", {}),
                "timestamp": result["timestamp"]
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "알 수 없는 오류가 발생했습니다.") if result else "데이터 수집 실패"
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# 캐시 데이터 조회 API (Supabase에서 로드)
# ========================================

@app.get("/api/cached-stock")
async def get_cached_stock():
    """Supabase에 저장된 재고 히스토리 데이터를 반환합니다."""
    try:
        from db import load_data
        cached = load_data("stock_history")
        if cached is not None:
            return {"success": True, "data": cached}
        return {"success": False, "data": {}, "error": "캐시된 재고 데이터가 없습니다."}
    except Exception as e:
        print(f"⚠️ 재고 캐시 로드 실패: {e}")
        return {"success": False, "data": {}, "error": str(e)}


@app.get("/api/cached-receiving")
async def get_cached_receiving():
    """Supabase에 저장된 입고 히스토리 데이터를 반환합니다."""
    try:
        from db import load_data
        cached = load_data("receiving_history")
        if cached is not None:
            return {"success": True, "data": cached}
        return {"success": False, "data": {}, "error": "캐시된 입고 데이터가 없습니다."}
    except Exception as e:
        print(f"⚠️ 입고 캐시 로드 실패: {e}")
        return {"success": False, "data": {}, "error": str(e)}


@app.get("/api/cached-ad")
async def get_cached_ad():
    """Supabase에 저장된 광고 히스토리 데이터를 반환합니다."""
    try:
        from db import load_data
        cached = load_data("ad_history")
        if cached is not None:
            return {"success": True, "data": cached}
        return {"success": False, "data": {}, "error": "캐시된 광고 데이터가 없습니다."}
    except Exception as e:
        print(f"⚠️ 광고 캐시 로드 실패: {e}")
        return {"success": False, "data": {}, "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
