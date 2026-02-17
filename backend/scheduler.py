"""
자동 데이터 업데이트 스케줄러
APScheduler를 사용하여 매일 정해진 시간에 모든 데이터를 자동으로 수집합니다.
"""

import os
import json
import time
from datetime import datetime, timedelta
from threading import Lock
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from scraper import fetch_stock_data, fetch_receiving_data, fetch_deduction_data

# 환경변수 로드
load_dotenv()

# 설정
COUPANG_USER_ID = os.getenv("COUPANG_USER_ID")
COUPANG_USER_PW = os.getenv("COUPANG_USER_PW")
AUTO_UPDATE_ENABLED = os.getenv("AUTO_UPDATE_ENABLED", "true").lower() == "true"
AUTO_UPDATE_HOUR = int(os.getenv("AUTO_UPDATE_HOUR", "9"))
AUTO_UPDATE_MINUTE = int(os.getenv("AUTO_UPDATE_MINUTE", "15"))

# 데이터 저장 경로
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# 동시 실행 방지를 위한 Lock
update_lock = Lock()
is_updating = False

# 마지막 업데이트 정보 저장
last_update_info = {
    "last_run": None,
    "last_success": None,
    "stock_count": 0,
    "receiving_count": 0,
    "deduction_count": 0,
    "errors": [],
    "is_running": False
}


def save_data_to_file(data, filename):
    """데이터를 Supabase DB에 저장 (로컬 JSON 파일에도 백업)"""
    key = filename.replace(".json", "")

    # 1. Supabase DB에 저장
    try:
        from db import save_data
        save_data(key, data)
        print(f"✅ DB 저장 완료: {key}")
    except Exception as e:
        print(f"⚠️ DB 저장 실패 (로컬 파일로 대체): {e}")

    # 2. 로컬 파일에도 백업 저장
    filepath = os.path.join(DATA_DIR, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return True


def load_data_from_file(filename):
    """Supabase DB에서 데이터 로드 (실패 시 로컬 파일에서 로드)"""
    key = filename.replace(".json", "")

    # 1. Supabase DB에서 로드 시도
    try:
        from db import load_data
        result = load_data(key)
        if result is not None:
            return result
    except Exception as e:
        print(f"⚠️ DB 로드 실패 (로컬 파일로 대체): {e}")

    # 2. 로컬 파일에서 로드 (폴백)
    filepath = os.path.join(DATA_DIR, filename)
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
    except Exception as e:
        print(f"❌ 데이터 로드 실패: {e}")
        return None


def auto_update_all_data():
    """모든 데이터를 자동으로 업데이트하는 메인 함수"""
    global last_update_info, is_updating

    # 동시 실행 방지: 이미 업데이트 중이면 스킵
    if not update_lock.acquire(blocking=False):
        print("⚠️ 이미 업데이트가 진행 중입니다. 현재 요청을 건너뜁니다.")
        return

    try:
        is_updating = True
        last_update_info["is_running"] = True

        print("\n" + "="*60)
        print(f"🤖 자동 업데이트 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)

        last_update_info["last_run"] = datetime.now().isoformat()
        last_update_info["errors"] = []

        if not COUPANG_USER_ID or not COUPANG_USER_PW or COUPANG_USER_ID == "your_coupang_id":
            error_msg = "⚠️ .env 파일에 쿠팡 로그인 정보를 입력해주세요!"
            print(error_msg)
            last_update_info["errors"].append(error_msg)
            return

        # 1. 재고 데이터 수집
        print("\n📦 [1/3] 재고 데이터 수집 중...")
        try:
            stock_result = fetch_stock_data(COUPANG_USER_ID, COUPANG_USER_PW, include_ad_report=True)
            if stock_result.get("success"):
                save_data_to_file(stock_result, "stock_data.json")
                last_update_info["stock_count"] = stock_result.get("count", 0)
                
                # 광고 데이터 로깅
                if stock_result.get("ad_data"):
                    print(f"✅ 광고 데이터 수집 완료: {stock_result.get('ad_data')}")
                
                print(f"✅ 재고 데이터 수집 완료: {last_update_info['stock_count']}개")
            else:
                error_msg = f"재고 데이터 수집 실패: {stock_result.get('error')}"
                print(f"❌ {error_msg}")
                last_update_info["errors"].append(error_msg)
        except Exception as e:
            error_msg = f"재고 데이터 수집 중 오류: {str(e)}"
            print(f"❌ {error_msg}")
            last_update_info["errors"].append(error_msg)

        # 대기 시간 (서버 부하 방지)
        time.sleep(5)

        # 2. 입고 데이터 수집
        print("\n📥 [2/3] 입고 데이터 수집 중...")
        try:
            receiving_result = fetch_receiving_data(COUPANG_USER_ID, COUPANG_USER_PW)
            if receiving_result.get("success"):
                save_data_to_file(receiving_result, "receiving_data.json")
                last_update_info["receiving_count"] = receiving_result.get("count", 0)
                print(f"✅ 입고 데이터 수집 완료: {last_update_info['receiving_count']}개")
            else:
                error_msg = f"입고 데이터 수집 실패: {receiving_result.get('error')}"
                print(f"❌ {error_msg}")
                last_update_info["errors"].append(error_msg)
        except Exception as e:
            error_msg = f"입고 데이터 수집 중 오류: {str(e)}"
            print(f"❌ {error_msg}")
            last_update_info["errors"].append(error_msg)

        # 대기 시간
        time.sleep(5)

        # 3. 정산내역 데이터 수집 (스마트 조회: 최근 5일 데이터 갱신 & 이전 데이터 보존)
        print("\n💰 [3/3] 정산내역 데이터 수집 중...")
        try:
            # 5일 전부터 오늘까지 갱신
            today = datetime.now()
            # 오늘 포함 5일치. 따라서 timedelta(days=4) 적용.
            buffer_date = today - timedelta(days=4)
            start_year = buffer_date.year
            start_month = buffer_date.month
            threshold_str = buffer_date.strftime('%Y-%m-%d')

            print(f"📅 스마트 수집: {threshold_str} 이후 데이터 갱신 (이전 데이터 보존)")
            
            result = fetch_deduction_data(
                COUPANG_USER_ID,
                COUPANG_USER_PW,
                start_year=start_year,
                start_month=start_month
            )
            
            if result.get("success"):
                new_data = result.get("data", [])
                
                # 기존 데이터 로드
                raw_existing = load_data_from_file("deduction_data.json")
                existing_data = []
                if isinstance(raw_existing, list):
                    existing_data = raw_existing
                elif isinstance(raw_existing, dict):
                    existing_data = raw_existing.get("data", [])

                # 날짜 추출 헬퍼 함수
                def get_row_date(row):
                    return row.get('증빙일') or row.get('매출발생일') or row.get('정산일') or ''

                # 기존 데이터 중 3일 전 이전의 것만 유지 (누적 보존)
                filtered_data = [
                    row for row in existing_data
                    if get_row_date(row) < threshold_str
                ]

                # 새 데이터 중 3일 전 이후의 것만 필터링 (갱신 대상)
                new_data_filtered = [
                    row for row in new_data
                    if get_row_date(row) >= threshold_str
                ]

                # 새 데이터 추가
                filtered_data.extend(new_data_filtered)

                # 저장
                save_result_obj = {
                    "success": True,
                    "data": filtered_data,
                    "count": len(filtered_data),
                    "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                save_data_to_file(save_result_obj, "deduction_data.json")
                last_update_info["deduction_count"] = len(filtered_data)
                print(f"✅ 정산내역 데이터 수집 완료: 총 {len(filtered_data)}개 (갱신 {len(new_data)}개)")
            else:
                error_msg = f"정산내역 데이터 수집 실패: {result.get('error')}"
                print(f"❌ {error_msg}")
                last_update_info["errors"].append(error_msg)
        except Exception as e:
            error_msg = f"정산내역 데이터 수집 중 오류: {str(e)}"
            print(f"❌ {error_msg}")
            last_update_info["errors"].append(error_msg)

        # 업데이트 정보 저장
        if len(last_update_info["errors"]) == 0:
            last_update_info["last_success"] = datetime.now().isoformat()

        save_data_to_file(last_update_info, "update_info.json")

        print("\n" + "="*60)
        if len(last_update_info["errors"]) == 0:
            print("🎉 자동 업데이트 완료!")
        else:
            print(f"⚠️ 자동 업데이트 완료 (오류 {len(last_update_info['errors'])}건)")
        print("="*60 + "\n")

    finally:
        # Lock 해제 및 상태 업데이트
        is_updating = False
        last_update_info["is_running"] = False
        update_lock.release()


def get_last_update_info():
    """마지막 업데이트 정보 조회"""
    info = load_data_from_file("update_info.json")
    return info if info else last_update_info


# 스케줄러 초기화
scheduler = BackgroundScheduler(timezone="Asia/Seoul")


def start_scheduler():
    """스케줄러 시작"""
    if not AUTO_UPDATE_ENABLED:
        print("ℹ️ 자동 업데이트가 비활성화되어 있습니다.")
        return

    # 매일 지정된 시간에 실행
    trigger = CronTrigger(hour=AUTO_UPDATE_HOUR, minute=AUTO_UPDATE_MINUTE, timezone="Asia/Seoul")
    scheduler.add_job(
        auto_update_all_data,
        trigger=trigger,
        id="auto_update_job",
        name="자동 데이터 업데이트",
        replace_existing=True
    )

    scheduler.start()
    print(f"✅ 자동 업데이트 스케줄러 시작!")
    print(f"   ⏰ 매일 {AUTO_UPDATE_HOUR:02d}:{AUTO_UPDATE_MINUTE:02d}에 실행됩니다.")
    print(f"   📍 현재 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def stop_scheduler():
    """스케줄러 중지"""
    if scheduler.running:
        scheduler.shutdown()
        print("🛑 자동 업데이트 스케줄러 중지")


if __name__ == "__main__":
    # 테스트: 즉시 업데이트 실행
    print("🧪 테스트 모드: 자동 업데이트 즉시 실행")
    auto_update_all_data()
