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
from scraper import fetch_stock_data, fetch_receiving_data, fetch_deduction_data, fetch_ad_report_only

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


def _calculate_days_back():
    """마지막 성공 수집일 기준으로 며칠치를 catch-up 해야 하는지 계산"""
    info = load_data_from_file("update_info.json")
    last_success_str = (info.get("last_success", "") or "") if info else ""
    days_back = 1  # 기본: 어제~오늘
    if last_success_str:
        try:
            last_success_dt = datetime.fromisoformat(last_success_str)
            missed_days = (datetime.now() - last_success_dt).days
            if missed_days > 1:
                days_back = min(missed_days, 14)  # 최대 14일까지 catch-up
        except Exception:
            pass
    return days_back


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

        # === 통합 catch-up 계산 (모든 수집에 공통 적용) ===
        days_back = _calculate_days_back()
        if days_back > 1:
            print(f"\n📌 놓친 날짜 감지: {days_back}일치 catch-up 모드")
        else:
            print(f"\n📌 일반 수집 모드 (어제~오늘)")

        # ──────────────────────────────────────────────
        # [1/4] 재고 데이터 수집 (현재 스냅샷)
        # ──────────────────────────────────────────────
        print(f"\n📦 [1/4] 재고 데이터 수집 중...")
        try:
            stock_result = fetch_stock_data(COUPANG_USER_ID, COUPANG_USER_PW, include_ad_report=False)
            if stock_result.get("success"):
                save_data_to_file(stock_result, "stock_data.json")
                last_update_info["stock_count"] = stock_result.get("count", 0)
                print(f"✅ 재고 데이터 수집 완료: {last_update_info['stock_count']}개")
            else:
                error_msg = f"재고 데이터 수집 실패: {stock_result.get('error')}"
                print(f"❌ {error_msg}")
                last_update_info["errors"].append(error_msg)
        except Exception as e:
            error_msg = f"재고 데이터 수집 중 오류: {str(e)}"
            print(f"❌ {error_msg}")
            last_update_info["errors"].append(error_msg)

        time.sleep(5)

        # ──────────────────────────────────────────────
        # [2/2] 정산내역 데이터 수집 (days_back 기반 스마트 조회)
        # ──────────────────────────────────────────────
        # 참고: 광고/입고는 봇 감지 문제로 자동 수집에서 제외
        #       프론트엔드에서 수동 버튼으로 수집 가능
        print(f"\n💰 [2/2] 정산내역 데이터 수집 중...")
        try:
            today = datetime.now()
            # 놓친 날짜와 기본 5일 중 더 큰 값 사용
            buffer_days = max(days_back, 4)
            buffer_date = today - timedelta(days=buffer_days)
            start_year = buffer_date.year
            start_month = buffer_date.month

            print(f"📅 월별 병합 수집: {start_year}년 {start_month}월부터 조회")

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

                # 월별 병합: 새로 수집한 월의 데이터는 전체 교체, 나머지 월 보존
                new_months = set(r.get("_query_month", "") for r in new_data if r.get("_query_month"))
                kept_existing = [r for r in existing_data if r.get("_query_month", "") not in new_months]
                merged_data = kept_existing + new_data

                # 로컬 파일 저장
                save_result_obj = {
                    "success": True,
                    "data": merged_data,
                    "count": len(merged_data),
                    "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                save_data_to_file(save_result_obj, "deduction_data.json")
                # Supabase에도 저장 (동일한 월별 병합)
                try:
                    from db import save_data as db_save, load_data as db_load
                    db_existing = db_load("deduction_data") or {}
                    old_db_records = db_existing.get("data", [])
                    kept_db = [r for r in old_db_records if r.get("_query_month", "") not in new_months]
                    merged_db = kept_db + new_data
                    db_save("deduction_data", {
                        "success": True,
                        "data": merged_db,
                        "count": len(merged_db),
                        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
                    print(f"✅ Supabase 정산 병합 저장 ({len(merged_db)}건)")
                except Exception as db_err:
                    print(f"⚠️ Supabase 정산 저장 실패: {db_err}")
                last_update_info["deduction_count"] = len(merged_data)
                print(f"✅ 정산내역 수집 완료: 총 {len(merged_data)}개 (보존 {len(kept_existing)}개 + 신규 {len(new_data)}개)")
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
            print("🎉 자동 업데이트 완료! (4/4 성공)")
        else:
            print(f"⚠️ 자동 업데이트 완료 (오류 {len(last_update_info['errors'])}건)")
        print("="*60 + "\n")

    finally:
        # Lock 해제 및 상태 업데이트
        is_updating = False
        last_update_info["is_running"] = False
        save_data_to_file(last_update_info, "update_info.json")
        update_lock.release()


def get_last_update_info():
    """마지막 업데이트 정보 조회"""
    info = load_data_from_file("update_info.json")
    return info if info else last_update_info


def check_and_collect_if_needed():
    """오늘 수집이 안 되어 있으면 자동으로 수집 실행 (잠자기 복귀 대응)"""
    today_str = datetime.now().strftime('%Y-%m-%d')
    info = get_last_update_info()
    last_success = info.get("last_success", "") or ""

    if not last_success.startswith(today_str):
        print(f"\n🔄 주기적 체크: 오늘({today_str}) 수집 이력 없음 → 자동 수집 시작")
        auto_update_all_data()
    else:
        print(f"🔄 주기적 체크: 오늘 이미 수집 완료 ({last_success[:16]})")


# 스케줄러 초기화
scheduler = BackgroundScheduler(timezone="Asia/Seoul")


def start_scheduler():
    """스케줄러 시작"""
    if not AUTO_UPDATE_ENABLED:
        print("ℹ️ 자동 업데이트가 비활성화되어 있습니다.")
        return

    # 매일 지정된 시간에 실행 (misfire_grace_time: 잠자기에서 깨어나도 3시간 이내면 실행)
    trigger = CronTrigger(hour=AUTO_UPDATE_HOUR, minute=AUTO_UPDATE_MINUTE, timezone="Asia/Seoul")
    scheduler.add_job(
        auto_update_all_data,
        trigger=trigger,
        id="auto_update_job",
        name="자동 데이터 업데이트",
        replace_existing=True,
        misfire_grace_time=10800
    )

    # 30분마다 오늘 수집 여부 체크 (잠자기에서 깨어나도 동작)
    scheduler.add_job(
        check_and_collect_if_needed,
        trigger='interval',
        minutes=30,
        id="periodic_check_job",
        name="주기적 수집 여부 체크",
        replace_existing=True,
        misfire_grace_time=3600
    )

    scheduler.start()
    print(f"✅ 자동 업데이트 스케줄러 시작!")
    print(f"   ⏰ 매일 {AUTO_UPDATE_HOUR:02d}:{AUTO_UPDATE_MINUTE:02d}에 실행됩니다.")
    print(f"   🔄 30분마다 미수집 체크")
    print(f"   📍 현재 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 오늘 수집 안 했으면 30초 후 자동 실행 (서버 시작 시 보충)
    today_str = datetime.now().strftime('%Y-%m-%d')
    info = get_last_update_info()
    last_success = info.get("last_success", "") or ""
    if not last_success.startswith(today_str):
        print(f"   📌 오늘 수집 이력 없음 → 30초 후 자동 수집 시작")
        scheduler.add_job(
            auto_update_all_data,
            trigger='date',
            run_date=datetime.now() + timedelta(seconds=30),
            id="startup_catchup_job",
            name="시작 시 보충 수집",
            replace_existing=True
        )
    else:
        print(f"   ✅ 오늘 이미 수집 완료 ({last_success[:16]})")


def stop_scheduler():
    """스케줄러 중지"""
    if scheduler.running:
        scheduler.shutdown()
        print("🛑 자동 업데이트 스케줄러 중지")


if __name__ == "__main__":
    # 테스트: 즉시 업데이트 실행
    print("🧪 테스트 모드: 자동 업데이트 즉시 실행")
    auto_update_all_data()
