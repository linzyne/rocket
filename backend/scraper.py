"""
쿠팡 광고 대시보드 재고 스크래핑 모듈
Selenium을 사용하여 쿠팡 광고 대시보드에서 재고 데이터를 수집합니다.
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc
import os
import time
import re
import tempfile
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from typing import List, Dict, Optional, Union

# 환경변수 기반 headless 모드 (배포 환경에서는 항상 headless)
HEADLESS_MODE = os.getenv("HEADLESS_MODE", "true").lower() == "true"


def create_chrome_driver(headless=False):
    """Google 계정 간섭 없이 깨끗한 Chrome 드라이버를 생성합니다."""
    uc_options = uc.ChromeOptions()
    if headless:
        uc_options.add_argument("--headless=new")
    uc_options.add_argument("--no-sandbox")
    uc_options.add_argument("--disable-dev-shm-usage")
    uc_options.add_argument("--disable-sync")
    uc_options.add_argument("--no-first-run")
    uc_options.add_argument("--disable-default-apps")
    uc_options.add_argument("--disable-background-networking")
    uc_options.add_argument("--disable-features=Translate,SignInPromo,IdentityConsistency")
    uc_options.add_argument("--noerrdialogs")
    driver = uc.Chrome(options=uc_options, user_data_dir=tempfile.mkdtemp(), version_main=145)
    # Google 계정 페이지가 뜬 경우 무시하고 넘어가기
    time.sleep(2)
    if "google.com" in driver.current_url:
        print("⚠️ Google 계정 페이지 감지 → 무시하고 진행합니다.")
        driver.get("about:blank")
        time.sleep(1)
    return driver


def do_login(driver, user_id, user_pw, label=""):
    """
    공통 로그인 함수: Keycloak/일반 로그인 폼 대응
    """
    try:
        pw_field = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']"))
        )

        # Keycloak (#username) 우선, 없으면 일반 셀렉터
        id_fields = driver.find_elements(By.CSS_SELECTOR, "#username")
        if not id_fields:
            id_fields = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='email']")
        id_field = id_fields[0]

        # 아이디 입력: Ctrl+A로 전체선택 후 덮어쓰기
        id_field.click()
        time.sleep(0.3)
        id_field.send_keys(Keys.CONTROL + "a")
        id_field.send_keys(Keys.COMMAND + "a")
        id_field.send_keys(user_id)
        time.sleep(0.3)

        # 비밀번호 입력
        pw_field.click()
        time.sleep(0.3)
        pw_field.send_keys(Keys.CONTROL + "a")
        pw_field.send_keys(Keys.COMMAND + "a")
        pw_field.send_keys(user_pw)
        time.sleep(0.5)

        # 입력값 확인 로그
        id_val = id_field.get_attribute("value")
        pw_val = pw_field.get_attribute("value")
        print(f"🔍 {label} 입력 확인 - ID: '{id_val}', PW 길이: {len(pw_val)}")

        # 로그인 버튼 클릭
        login_btn = driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
        if not login_btn:
            login_btn = driver.find_elements(By.XPATH, "//*[contains(text(),'로그인') and (self::button or self::a or self::input)]")
        if login_btn:
            login_btn[0].click()
        else:
            pw_field.send_keys(Keys.ENTER)

        print(f"✅ {label} 로그인 정보 입력 완료!")
        time.sleep(5)
        return True
    except Exception as e:
        print(f"⚠️ {label} 로그인 실패: {e}")
        return False


def extract_stock_from_page(driver) -> List[Dict]:
    """
    현재 페이지에서 재고 데이터를 추출합니다.

    Returns:
        List[Dict]: 상품명과 재고량 리스트
    """
    rows = []
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
        lines = [line.strip() for line in body_text.split('\n') if line.strip()]

        # UI 요소 및 불필요한 텍스트 필터링용 키워드 리스트
        exclude_keywords = [
            "•", "ID:", "위너", "아이템", "광고", "클릭",
            "버튼", "선택", "전체", "검색", "필터", "정렬",
            "탭", "메뉴", "설정", "저장", "취소", "확인",
            "로그인", "로그아웃", "마이페이지", "도움말",
            "이전", "다음", "페이지", "목록", "상세", "닫기",
            "등록", "수정", "삭제", "추가", "변경", "적용",
            "보기", "더보기", "접기", "펼치기", "새로고침",
            "시노토이즈"  # 사용자가 명시한 잘못된 상품명
        ]

        for i, line in enumerate(lines):
            # 1. 재고량 찾기 ('재고량:' 문구가 포함된 줄에서 숫자만 추출)
            if "재고량:" in line:
                # 재고량 위쪽 3줄을 확인해서 valid한 상품명 찾기
                # 구조: 상품명 / ID: ... / 재고량: X개
                candidate_lines = []
                for j in range(1, 4):  # 1~3줄 위를 확인
                    if i - j >= 0:
                        candidate_lines.append(lines[i - j])

                # 가장 valid한 상품명 찾기
                valid_product_name = None
                for candidate in candidate_lines:
                    # 상품명 유효성 검증
                    is_valid_product = True

                    # 제외 키워드 체크
                    for keyword in exclude_keywords:
                        if keyword in candidate:
                            is_valid_product = False
                            break

                    # 최소 길이 체크 (상품명은 보통 10자 이상)
                    if len(candidate) < 10:
                        is_valid_product = False

                    # 숫자만으로 구성되지 않았는지 체크
                    if candidate.replace(',', '').replace('.', '').replace('-', '').isdigit():
                        is_valid_product = False

                    # URL 또는 이메일 형식 제외
                    if 'http://' in candidate or 'https://' in candidate or '@' in candidate:
                        is_valid_product = False

                    # 날짜 형식 제외 (예: 2024-01-01)
                    if re.match(r'^\d{4}[-./]\d{1,2}[-./]\d{1,2}', candidate):
                        is_valid_product = False

                    # 한글, 영문, 숫자가 포함되어 있는지 체크 (최소한의 상품명 패턴)
                    if not re.search(r'[가-힣a-zA-Z]', candidate):
                        is_valid_product = False

                    if is_valid_product:
                        valid_product_name = candidate
                        break  # 첫 번째 valid한 상품명 사용

                if valid_product_name:
                    stock_number = re.sub(r'[^0-9]', '', line)
                    if stock_number:
                        rows.append({
                            "product_name": valid_product_name,
                            "stock": int(stock_number)
                        })
                        print(f"✅ 추출: {valid_product_name} → 재고 {stock_number}")

    except Exception as e:
        print(f"⚠️ 데이터 추출 중 오류: {e}")

    return rows


def fetch_stock_data(user_id: str, user_pw: str, debug_mode: bool = True, include_ad_report: bool = False) -> Dict:
    """
    쿠팡 광고 대시보드에서 재고 데이터를 수집합니다.
    광고하는상품 + 광고하지않는상품 모두 수집합니다.

    Args:
        user_id: 쿠팡 사용자 ID
        user_pw: 쿠팡 사용자 비밀번호
        debug_mode: 디버그 모드 (스크린샷 및 HTML 저장)

    Returns:
        Dict: 성공 시 재고 데이터, 실패 시 에러 메시지. include_ad_report=True인 경우 "ad_data" 키에 광고 데이터 포함.
    """
    driver = None
    try:
        print("🚀 [1단계] 브라우저 실행 중...")
        driver = create_chrome_driver(headless=HEADLESS_MODE and not debug_mode)

        driver.get("https://advertising.coupang.com/marketing/product-dashboard")
        time.sleep(7)

        # 1. 로그인 단계
        print("🔐 [2단계] 로그인 시도 중...")
        all_login_btns = driver.find_elements(By.XPATH, "//*[text()='로그인하기']")
        if len(all_login_btns) >= 2:
            driver.execute_script("arguments[0].click();", all_login_btns[1])

        do_login(driver, user_id, user_pw, label="[재고]")

        all_stock_data = []

        # 2. 첫 번째 탭(광고하지않는상품) 데이터 수집
        print("\n🔎 [3단계] 광고하지않는상품 데이터 수집 중...")
        for i in range(30):
            try:
                body_text = driver.find_element(By.TAG_NAME, "body").text

                # 디버그: 첫 번째 시도에서 페이지 상태 저장
                if debug_mode and i == 0:
                    print("🐛 [DEBUG] 광고하지않는상품 페이지 상태 저장 중...")
                    try:
                        driver.save_screenshot("debug_non_ad_products.png")
                        with open("debug_non_ad_products.txt", "w", encoding="utf-8") as f:
                            f.write(body_text[:5000])  # 처음 5000자만 저장
                        print(f"🐛 [DEBUG] 페이지 텍스트 일부: {body_text[:300]}")
                    except Exception as e:
                        print(f"⚠️ 디버그 저장 실패: {e}")

                if "아이템 위너" in body_text:
                    print("📊 광고하지않는상품 데이터 포착!")
                    non_ad_data = extract_stock_from_page(driver)
                    for item in non_ad_data:
                        item["ad_status"] = "광고안함"
                    all_stock_data.extend(non_ad_data)
                    print(f"✅ 광고하지않는상품: {len(non_ad_data)}개 수집")
                    break
                else:
                    if debug_mode and i == 0:
                        print(f"⚠️ '아이템 위너' 텍스트를 찾을 수 없습니다. 재시도 {i+1}/30")
            except Exception:
                pass
            time.sleep(2)
        
        # 3. 두 번째 탭(광고 중인 상품) 클릭 및 데이터 수집
        print("\n🔎 [4단계] 광고 중인 상품 데이터 수집 중...")
        try:
            # 디버그: 탭 찾기 전 페이지 상태
            if debug_mode:
                print("🐛 [DEBUG] 탭 찾기 전 페이지 상태 확인...")
                page_text = driver.find_element(By.TAG_NAME, "body").text
                print(f"🐛 [DEBUG] 현재 페이지에 있는 텍스트 일부: {page_text[:500]}")

            # "광고 중인 상품" 탭 찾기 및 클릭 (여러 패턴 시도)
            ad_tab = None

            # 패턴 1: "광고 중인 상품" 정확히 매칭
            ad_tab = driver.find_elements(By.XPATH, "//*[contains(text(), '광고 중인 상품')]")
            if ad_tab and debug_mode:
                print(f"🐛 [DEBUG] 패턴 1 매칭: {len(ad_tab)}개 발견")

            # 패턴 2: "광고하는 상품" (변경된 이름)
            if not ad_tab:
                ad_tab = driver.find_elements(By.XPATH, "//*[contains(text(), '광고하는 상품')]")
                if ad_tab and debug_mode:
                    print(f"🐛 [DEBUG] 패턴 2(광고하는 상품) 매칭: {len(ad_tab)}개 발견")

            # 패턴 3: "광고 중인" 포함
            if not ad_tab:
                ad_tab = driver.find_elements(By.XPATH, "//*[contains(text(), '광고 중인')]")
                if ad_tab and debug_mode:
                    print(f"🐛 [DEBUG] 패턴 3 매칭: {len(ad_tab)}개 발견")

            # 패턴 4: "광고중인" (공백 없이)
            if not ad_tab:
                ad_tab = driver.find_elements(By.XPATH, "//*[contains(text(), '광고중인')]")
                if ad_tab and debug_mode:
                    print(f"🐛 [DEBUG] 패턴 4 매칭: {len(ad_tab)}개 발견")

            # 패턴 5: 탭 역할을 하는 요소 중 "광고" 포함
            if not ad_tab:
                ad_tab = driver.find_elements(By.XPATH, "//div[contains(@class, 'tab') and contains(text(), '광고')]")
                if ad_tab and debug_mode:
                    print(f"🐛 [DEBUG] 패턴 5 매칭: {len(ad_tab)}개 발견")

            if ad_tab:
                if debug_mode:
                    print(f"🐛 [DEBUG] 탭 텍스트: {ad_tab[0].text}")
                driver.execute_script("arguments[0].click();", ad_tab[0])
                print("📌 광고 중인 상품 탭 클릭 성공!")
                time.sleep(7)  # 탭 전환 대기 (5초 → 7초로 증가)
                
                # 광고 중인 상품 데이터 수집
                for i in range(15):
                    try:
                        body_text = driver.find_element(By.TAG_NAME, "body").text

                        # 디버그: 첫 번째 시도에서 페이지 상태 저장
                        if debug_mode and i == 0:
                            print("🐛 [DEBUG] 광고 중인 상품 페이지 상태 저장 중...")
                            try:
                                driver.save_screenshot("debug_ad_products.png")
                                with open("debug_ad_products.txt", "w", encoding="utf-8") as f:
                                    f.write(body_text[:5000])
                                print(f"🐛 [DEBUG] 페이지 텍스트 일부: {body_text[:300]}")
                            except Exception as e:
                                print(f"⚠️ 디버그 저장 실패: {e}")

                        if "아이템 위너" in body_text or "재고량:" in body_text:
                            print("📊 광고 중인 상품 데이터 포착!")
                            ad_data = extract_stock_from_page(driver)
                            for item in ad_data:
                                item["ad_status"] = "광고중"
                            all_stock_data.extend(ad_data)
                            print(f"✅ 광고 중인 상품: {len(ad_data)}개 수집")
                            break
                        else:
                            if debug_mode and i == 0:
                                print(f"⚠️ '아이템 위너' 또는 '재고량:' 텍스트를 찾을 수 없습니다. 재시도 {i+1}/15")
                    except Exception:
                        pass
                    time.sleep(2)
            else:
                print("⚠️ 광고 중인 상품 탭을 찾을 수 없습니다.")
                if debug_mode:
                    print("🐛 [DEBUG] 탭을 찾지 못했습니다. 페이지 텍스트 전체 저장...")
                    try:
                        page_text = driver.find_element(By.TAG_NAME, "body").text
                        with open("debug_tab_not_found.txt", "w", encoding="utf-8") as f:
                            f.write(page_text)
                        print(f"🐛 [DEBUG] 페이지 텍스트 일부: {page_text[:500]}")
                    except Exception as e:
                        print(f"⚠️ 디버그 저장 실패: {e}")
        except Exception as e:
            print(f"⚠️ 광고하는상품 탭 처리 중 오류: {e}")

        if not all_stock_data:
            error_msg = "데이터를 찾을 수 없습니다. "
            if debug_mode:
                error_msg += "디버그 파일(debug_*.png, debug_*.txt)을 확인하세요."
            else:
                error_msg += "페이지 로딩에 실패했거나 로그인에 문제가 있을 수 있습니다."
            return {
                "success": False,
                "error": error_msg
            }

        # 4. 중복 제거
        seen = set()
        unique_rows = []
        for row in all_stock_data:
            key = (row["product_name"], row["stock"], row.get("ad_status", ""))
            unique_rows.append(row)

        result = {
            "success": True,
            "data": unique_rows,
            "count": len(unique_rows),
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
        }

        # 5. 광고 리포트 수집 (요청 시)
        if include_ad_report:
            print("\n📈 [5단계] 광고 리포트 수집 시작...")
            try:
                ad_data = fetch_ad_report(driver, debug_mode=debug_mode)
                if ad_data:
                    result["ad_data"] = ad_data
                    print(f"✅ 광고 리포트 수집 완료: {ad_data}")
                else:
                    print("⚠️ 광고 리포트 수집 실패 (데이터 없음)")
            except Exception as e:
                print(f"⚠️ 광고 리포트 수집 중 오류: {e}")
                result["ad_error"] = str(e)

        print(f"\n🎊 완료! 총 {len(unique_rows)}개 상품 데이터 수집")
        return result

    except Exception as e:
        print(f"❌ 에러 발생: {e}")
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        if driver:
            time.sleep(2)
            driver.quit()
            print("🔒 브라우저 종료")



def extract_number(text):
    if not text: return 0
    # 숫자, 소수점 제외 제거
    clean = re.sub(r'[^0-9.]', '', text)
    try:
        return float(clean) if '.' in clean else int(clean)
    except:
        return 0

def select_yesterday_date(driver):
    print("📅 [광고리포트] 날짜 '어제' 선택 중...")
    try:
        # '어제' 텍스트를 가진 버튼/탭 찾기
        yesterday_btns = driver.find_elements(By.XPATH, "//*[text()='어제']")
        if yesterday_btns:
            for btn in yesterday_btns:
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
                    print("📌 '어제' 버튼 클릭 성공")
                    time.sleep(5) # 데이터 로딩 대기
                    return True
        else:
            print("⚠️ '어제' 버튼을 찾을 수 없습니다.")
    except Exception as e:
        print(f"⚠️ 날짜 선택 중 오류: {e}")
    return False

def select_specific_date(driver, date_str):
    """
    광고 대시보드에서 특정 날짜를 선택합니다.
    date_str: 'YYYY-MM-DD' 형식
    """
    from datetime import datetime, timedelta
    # 어제 날짜인지 확인 - 어제면 기존 '어제' 버튼 사용
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    if date_str == yesterday:
        return select_yesterday_date(driver)

    print(f"📅 [광고리포트] 날짜 '{date_str}' 선택 중...")
    try:
        from selenium.webdriver.common.keys import Keys
        import platform

        # 방법 1: URL 파라미터로 날짜 지정하여 대시보드 로드
        target_url = f"https://advertising.coupang.com/marketing/dashboard/sales?dateType=CUSTOM&startDate={date_str}&endDate={date_str}"
        driver.get(target_url)
        time.sleep(4)

        page_text = driver.find_element(By.TAG_NAME, "body").text
        if date_str in page_text:
            print(f"   📌 날짜 '{date_str}' 적용 확인 (URL 파라미터)")
            return True

        print(f"   ⚠️ URL 파라미터 방식 실패, 날짜 직접 입력 시도...")

        # 방법 2: JS로 날짜 입력 필드 값 변경
        date_inputs = driver.find_elements(By.CSS_SELECTOR, ".ant-picker input, input[class*='date'], input[class*='Date']")
        for inp in date_inputs:
            if inp.is_displayed():
                try:
                    # JS로 값 설정 후 이벤트 트리거
                    driver.execute_script("""
                        var el = arguments[0];
                        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        nativeInputValueSetter.call(el, arguments[1]);
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    """, inp, date_str)
                    time.sleep(1)
                    inp.send_keys(Keys.ENTER)
                    time.sleep(3)
                    print(f"   📌 날짜 입력 완료 (JS): {date_str}")
                    return True
                except:
                    pass

                # 방법 3: 전체선택 + 타이핑
                inp.click()
                time.sleep(0.5)
                select_all = Keys.COMMAND + 'a' if platform.system() == 'Darwin' else Keys.CONTROL + 'a'
                inp.send_keys(select_all)
                inp.send_keys(date_str)
                inp.send_keys(Keys.ENTER)
                time.sleep(3)
                print(f"   📌 날짜 입력 완료 (키입력): {date_str}")
                return True

        print(f"   ⚠️ 날짜 입력 필드를 찾을 수 없습니다.")
    except Exception as e:
        print(f"⚠️ 날짜 선택 실패 ({date_str}): {e}")
    return False

def extract_product_table(driver):
    """
    캠페인 상세 페이지에서 상품별 데이터를 추출합니다.
    
    고정 컬럼 위치 (0-indexed):
      0: 상품명 | 5: 클릭률 | 6: 광고 전환 판매수 | 7: 광고 전환 매출
      8: 전환율 | 9: 집행 광고비 | 10: 광고수익률
    """
    print("📦 [광고리포트] 상세 데이터 추출 시작...")
    products = []
    
    # 고정 컬럼 인덱스 (사이트 실제 테이블 구조 기준)
    COL = {
        "product_name": 0,
        "ctr":          5,
        "ad_sales":     6,
        "ad_revenue":   7,
        "cvr":          8,
        "ad_cost":      9,
        "roas":         10
    }
    
    try:
        # 1. 성과 그래프 아래 테이블까지 스크롤
        for _ in range(3):
            driver.execute_script("window.scrollBy(0, 800);")
            time.sleep(1)
            
        # "상품명" 텍스트가 나타날 때까지 대기
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), '상품명')]"))
            )
            print("   ✅ '상품명' 헤더 확인 완료")
        except:
            print("   ⚠️ '상품명' 헤더를 찾을 수 없습니다.")

        # 2. 데이터 행 찾기
        rows = driver.find_elements(By.XPATH, "//table//tbody//tr")
        if not rows:
            rows = driver.find_elements(By.XPATH, "//div[contains(@role, 'row')]")
            rows = [r for r in rows if r.text and "상품명" not in r.text]

        print(f"   총 {len(rows)}개 행 분석 시작...")
        
        # 3. 각 행에서 고정 인덱스로 데이터 추출
        for row in rows:
            try:
                cells = row.find_elements(By.TAG_NAME, "td")
                if not cells:
                    cells = row.find_elements(By.XPATH, "./div | ./span")
                
                if len(cells) <= COL["roas"]:
                    continue  # 컬럼 수가 부족하면 스킵
                
                # 모든 광고 집행 상품 수집 (판매수 0이어도 광고비가 나갔을 수 있으므로)
                ad_sales_val = extract_number(cells[COL["ad_sales"]].text)
                
                p_data = {
                    "product_name": cells[COL["product_name"]].text.strip(),
                    "ctr":          extract_number(cells[COL["ctr"]].text),
                    "ad_sales":     ad_sales_val,
                    "ad_revenue":   extract_number(cells[COL["ad_revenue"]].text),
                    "cvr":          extract_number(cells[COL["cvr"]].text),
                    "ad_cost":      extract_number(cells[COL["ad_cost"]].text),
                    "roas":         extract_number(cells[COL["roas"]].text)
                }
                
                products.append(p_data)
                print(f"      ✅ {p_data['product_name'][:20]} | 판매:{p_data['ad_sales']} | 매출:{p_data['ad_revenue']} | 광고비:{p_data['ad_cost']} | ROAS:{p_data['roas']}%")
                    
            except Exception as e:
                print(f"      ⚠️ 행 처리 중 오류: {e}")
                continue
             
    except Exception as e:
        print(f"⚠️ 상품 상세 데이터 추출 실패: {e}")
        
    return products

def fetch_ad_report(driver, target_date='yesterday', debug_mode=True, collect_campaign_details=True) -> Optional[Dict]:
    """
    현재 로그인된 드라이버 세션을 사용하여 광고 리포트를 수집합니다.
    '광고표준' 대시보드로 이동하여 요약 데이터 및 캠페인별 상세 데이터를 수집합니다.
    """
    try:
        print(f"📊 [광고리포트] 대시보드 페이지로 이동 중... (날짜: {target_date})")

        # 1. 사용자 지정 URL로 이동 ('광고표준' 대시보드)
        target_url = "https://advertising.coupang.com/marketing/dashboard/sales"

        # 최대 3회 대시보드 이동 시도
        for nav_attempt in range(3):
            driver.get(target_url)
            time.sleep(3 + nav_attempt * 2)
            if "marketing/dashboard" in driver.current_url or "dashboard/sales" in driver.current_url:
                break
            print(f"⚠️ 페이지 이동 실패 (시도 {nav_attempt+1}/3): {driver.current_url}")

        if "marketing/dashboard" not in driver.current_url and "dashboard/sales" not in driver.current_url:
            print(f"❌ 대시보드 이동 불가 → 이 날짜({target_date}) 건너뜀")
            return None

        # 2. 날짜 선택
        if target_date == 'yesterday':
            select_yesterday_date(driver)
        else:
            select_specific_date(driver, target_date)

        # 3. 데이터 추출 (요약 데이터)
        print("Reading [광고리포트] 요약 데이터 추출 중...")
        
        result = {}
        targets = {
            "전체 집행 광고비": "ad_cost",
            "전체 판매수": "total_sales",
            "광고 전환 판매수": "ad_sales",
            "광고 수익률": "roas",
            "전환율": "conversion_rate"
        }
        
        # 데이터가 로드될 때까지 최대 3회 재시도 (요약 데이터)
        for attempt in range(3):
            print(f"   요약 데이터 추출 시도 {attempt+1}/3...")
            
            for keyword, key in targets.items():
                if key in result and result[key] > 0: continue
                
                try:
                    elements = driver.find_elements(By.XPATH, f"//*[contains(text(), '{keyword}')]")
                    found = False
                    for el in elements:
                        if not el.is_displayed(): continue
                        
                        try:
                            value_el = el.find_element(By.XPATH, "./following-sibling::*[1]")
                            text = value_el.text.strip()
                            if text and (text[0].isdigit() or text.startswith('₩') or text.startswith('$')):
                                val = extract_number(text)
                                result[key] = val
                                found = True
                                print(f"✅ {keyword}: {text} -> {val}")
                                break
                        except: pass
                        
                        if not found:
                            try:
                                parent = el.find_element(By.XPATH, "..")
                                value_el = parent.find_element(By.XPATH, "./following-sibling::*[1]")
                                text = value_el.text.strip()
                                if text and (text[0].isdigit() or text.startswith('₩') or text.startswith('$')):
                                    val = extract_number(text)
                                    result[key] = val
                                    found = True
                                    print(f"✅ {keyword} (부모형제): {text} -> {val}")
                                    break
                            except: pass
                except Exception as e:
                    pass
            
            if 'ad_cost' in result or 'total_sales' in result:
                break
            time.sleep(2)
        
        # 4. 광고비 10% 가산
        if 'ad_cost' in result:
            original_cost = result['ad_cost']
            result['ad_cost_original'] = original_cost
            result['ad_cost'] = int(original_cost * 1.1)
            print(f"💰 광고비 조정: {original_cost} -> {result['ad_cost']} (+10%)")
        else:
            print("⚠️ 광고비 데이터를 찾지 못했습니다.")
            # 광고비를 못 찾으면 실패로 처리 (다음에 재수집하도록)
            return None

        # 5. 캠페인별 상세 데이터 수집 (Nested Scraping)
        if not collect_campaign_details:
            result['products'] = []
            return result

        print("📦 [광고리포트] 캠페인별 상세 데이터 수집 시작 (Nested Scraping)...")
        all_products = []

        try:
            # 5-1. 활성 캠페인 탐색 (ON 토글 버튼 기반)
            campaign_targets = [] # {'type': 'url', 'val': url} or {'type': 'click', 'index': i}
            
            # 테이블 데이터가 로드될 때까지 대기
            time.sleep(2)
            
            # ON 요소 탐색 (태그 종류 불문 - 실제 태그 확인용 디버깅 포함)
            all_on_elements = driver.find_elements(By.XPATH, "//*[text()='ON']")
            print(f"   🔎 'ON' 텍스트 요소 {len(all_on_elements)}개 발견")
            
            # 각 ON 요소의 태그명, 클래스, 부모 정보를 출력 (디버깅)
            on_buttons = []
            for idx, el in enumerate(all_on_elements):
                try:
                    tag = el.tag_name
                    cls = el.get_attribute("class") or ""
                    role = el.get_attribute("role") or ""
                    parent_tag = el.find_element(By.XPATH, "./..").tag_name
                    parent_cls = el.find_element(By.XPATH, "./..").get_attribute("class") or ""
                    visible = el.is_displayed()
                    print(f"      [{idx}] 태그:{tag} | 클래스:{cls[:50]} | role:{role} | 부모:{parent_tag}.{parent_cls[:30]} | 표시:{visible}")
                    if visible:
                        on_buttons.append(el)
                except Exception as e:
                    print(f"      [{idx}] 분석 실패: {e}")
            
            print(f"   ✅ 표시된 ON 요소 {len(on_buttons)}개를 수집 대상으로 사용")
            
            for i, el in enumerate(on_buttons):
                try:
                    if not el.is_displayed(): continue
                    
                    # 해당 ON 요소와 연결된 링크 찾기
                    # 전략 1: 바로 앞에 있는 a 태그 (행 구조상 보통 제목이 앞에 있음)
                    # 전략 2: 가장 가까운 상위 tr/div[role='row'] 내의 첫번째 a 태그
                    
                    target_url = None
                    found_link = False
                    
                    # 전략 1 시도
                    try:
                        link = el.find_element(By.XPATH, "./preceding::a[1]")
                        url = link.get_attribute("href")
                        if url:
                            target_url = url
                            found_link = True
                            # print(f"      🔗 링크 발견 (Strategy 1): {url}")
                    except: pass
                    
                    # 전략 2 시도 (전략 1 실패 시)
                    if not found_link:
                        try:
                            # 상위 요소로 이동하면서 a 태그 검색
                            parent = el.find_element(By.XPATH, "./..")
                            for _ in range(3): # 최대 3단계 상위까지
                                links = parent.find_elements(By.TAG_NAME, "a")
                                if links:
                                    target_url = links[0].get_attribute("href")
                                    found_link = True
                                    # print(f"      🔗 링크 발견 (Strategy 2): {target_url}")
                                    break
                                parent = parent.find_element(By.XPATH, "./..")
                        except: pass
                    
                    # 수집 대상 추가
                    if found_link and target_url and "http" in target_url:
                        if not any(t['val'] == target_url for t in campaign_targets if t['type'] == 'url'):
                             campaign_targets.append({'type': 'url', 'val': target_url})
                             print(f"      ✅ 수집 대상 추가 (URL): {target_url}")
                    else:
                        # URL이 없거나 JS 링크인 경우 클릭 방식 사용
                        campaign_targets.append({'type': 'click', 'index': i})
                        print(f"      ✅ 수집 대상 추가 (Click): Index {i}")

                except Exception as e:
                    print(f"      ⚠️ 요소 분석 중 오류: {e}")
                    continue

            print(f"   총 {len(campaign_targets)}개의 수집 대상 캠페인을 식별했습니다.")
            
            # [디버깅] 캠페인을 하나도 못 찾았다면 페이지 상태 분석 정보 출력
            if not campaign_targets:
                print("\n🔍 [디버깅] 캠페인 탐색 실패 분석")
                print(f"      - 현재 URL: {driver.current_url}")
                print(f"      - 페이지 제목: {driver.title}")
                
                body_text = driver.find_element(By.TAG_NAME, "body").text
                has_on = "ON" in body_text
                has_running = "운영" in body_text
                print(f"      - 페이지 내 'ON' 텍스트 존재 여부: {has_on}")
                print(f"      - 페이지 내 '운영' 텍스트 존재 여부: {has_running}")
                
                # 테이블 행 데이터 샘플 출력
                rows = driver.find_elements(By.TAG_NAME, "tr")
                print(f"      - 발견된 테이블 행(tr) 개수: {len(rows)}")
                if rows:
                    print("      - 상위 3개 행 텍스트 샘플:")
                    for i, r in enumerate(rows[:3]):
                        print(f"        [{i}] {r.text[:50]}...")
                
                # iframe 여부 확인
                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                if iframes:
                    print(f"      ⚠️ 경고: 페이지에 iframe {len(iframes)}개가 존재합니다. 데이터가 iframe 안에 있을 수 있습니다.")

            # 5-2. 순회 및 데이터 수집
            current_dashboard_url = driver.current_url

            for i, target in enumerate(campaign_targets):
                print(f"   🚀 [{i+1}/{len(campaign_targets)}] 상세 페이지 진입 시도...")
                
                try:
                    entered = False
                    
                    if target['type'] == 'url':
                        driver.get(target['val'])
                        time.sleep(3)

                        # URL 이동 후에도 제대로 로드되었는지 확인
                        if "campaignId" not in driver.current_url and "marketing/campaigns" not in driver.current_url:
                             print(f"      ⚠️ 경고: 예상치 못한 페이지로 이동함 ({driver.current_url})")

                        entered = True
                    else:
                        # 클릭 방식 (Stale Element 방지를 위해 다시 찾기)
                        try:
                            # 대시보드로 복귀 확인
                            if driver.current_url != current_dashboard_url:
                                driver.get(current_dashboard_url)
                                time.sleep(3)

                            # ON 요소 다시 찾기 (span.ant-switch-inner 등)
                            all_on = driver.find_elements(By.XPATH, "//*[text()='ON']")
                            visible_on = [e for e in all_on if e.is_displayed()]

                            if target['index'] < len(visible_on):
                                target_el = visible_on[target['index']]

                                # ON 요소에서 상위로 올라가며 같은 행의 링크(a) 찾기
                                link = None
                                parent = target_el
                                for _ in range(10):  # 최대 10단계 상위 탐색
                                    parent = parent.find_element(By.XPATH, "./..")
                                    links = parent.find_elements(By.TAG_NAME, "a")
                                    if links:
                                        link = links[0]
                                        break

                                if link:
                                    url = link.get_attribute("href")
                                    if url and "http" in url:
                                        print(f"      🖱 링크 발견 → 이동: {link.text[:30]}")
                                        driver.get(url)
                                    else:
                                        print(f"      🖱 클릭 실행: {link.text[:30]}")
                                        driver.execute_script("arguments[0].click();", link)
                                    time.sleep(3)
                                    entered = True
                                else:
                                    print("      ⚠️ ON 요소 주변에서 링크를 찾을 수 없음")
                            else:
                                print(f"      ⚠️ 요소를 다시 찾을 수 없음 (visible: {len(visible_on)}, index: {target['index']})")
                        except Exception as e:
                            print(f"      ⚠️ 클릭 진입 실패: {e}")

                    if entered:
                        # 날짜 선택 및 데이터 추출
                        select_yesterday_date(driver)
                        products = extract_product_table(driver)
                        if products:
                            print(f"      ✅ {len(products)}개 상품 데이터 추출됨")
                            all_products.extend(products)
                        else:
                            print("      ⚠️ 상품 데이터 없음")

                except Exception as e:
                    print(f"      ⚠️ 캠페인 처리 중 오류: {e}")
            
        except Exception as e:
            print(f"⚠️ 캠페인별 상세 수집 중 오류: {e}")
            import traceback
            traceback.print_exc()

        # 중복 제거 (여러 캠페인에서 같은 상품이 수집될 수 있음)
        seen_names = set()
        unique_products = []
        for p in all_products:
            name = p.get('product_name', '')
            if name and name not in seen_names:
                seen_names.add(name)
                unique_products.append(p)
        
        if len(unique_products) < len(all_products):
            print(f"   🔄 중복 제거: {len(all_products)}개 → {len(unique_products)}개")
        
        result['products'] = unique_products
        return result

    except Exception as e:
        print(f"❌ 광고 리포트 수집 중 치명적 오류: {e}")
        import traceback
        traceback.print_exc()
        return None

def fetch_ad_report_only(user_id: str, user_pw: str, days_back: int = 1, debug_mode: bool = True, skip_dates: set = None) -> Dict:
    """
    광고 리포트 데이터만 독립적으로 수집합니다.
    days_back일치 데이터를 수집하며, 캠페인 상세는 어제분만 수집합니다.
    skip_dates: 이미 수집된 날짜 set (건너뛰기)
    """
    if skip_dates is None:
        skip_dates = set()

    driver = None
    try:
        from datetime import datetime, timedelta

        print(f"🚀 [광고수집 1단계] 브라우저 실행 중... ({days_back}일치 수집, {len(skip_dates)}개 스킵)")
        driver = create_chrome_driver(headless=HEADLESS_MODE and not debug_mode)

        driver.get("https://advertising.coupang.com/marketing/campaigns")
        time.sleep(5)

        # 1. 로그인
        print("🔐 [광고수집 2단계] 로그인 시도 중...")
        all_login_btns = driver.find_elements(By.XPATH, "//*[text()='로그인하기']")
        if len(all_login_btns) >= 2:
            driver.execute_script("arguments[0].click();", all_login_btns[1])

        try:
            do_login(driver, user_id, user_pw, label="[광고]")
            time.sleep(4)
            current_url = driver.current_url
            if "product-dashboard" in current_url or "login" in current_url:
                target_url = "https://advertising.coupang.com/marketing/dashboard/sales"
                print(f"⚡️ [광고수집] 현재 페이지({current_url}) -> 광고 대시보드로 이동: {target_url}")
                driver.get(target_url)
                time.sleep(4)
        except Exception as login_err:
            print(f"⚠️ 로그인 폼 찾기 실패: {login_err}")

        # 2. 광고 리포트 수집 (days_back일치)
        yesterday_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        actual_count = days_back - len(skip_dates)
        print(f"\n📈 [광고수집 3단계] 광고 리포트 {actual_count}일치 데이터 추출...")
        data_by_date = {}
        collected = 0

        for i in range(days_back, 0, -1):
            target_date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')

            # 이미 수집된 날짜 건너뛰기
            if target_date in skip_dates:
                print(f"   ⏩ {target_date} 이미 수집됨 → 건너뜀")
                continue

            collected += 1
            is_yesterday = (target_date == yesterday_str)
            print(f"\n📅 [{collected}/{actual_count}] {target_date} 수집 중... (상세: {'O' if is_yesterday else 'X'})")

            ad_data = fetch_ad_report(
                driver,
                target_date=target_date,
                debug_mode=debug_mode,
                collect_campaign_details=is_yesterday
            )

            if ad_data:
                data_by_date[target_date] = ad_data
                print(f"   ✅ {target_date} 수집 완료")
            else:
                print(f"   ⚠️ {target_date} 수집 실패")

        if data_by_date:
            return {
                "success": True,
                "data_by_date": data_by_date,
                "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
            }
        else:
            return {
                "success": False,
                "error": "광고 데이터를 찾을 수 없습니다."
            }

    except Exception as e:
        print(f"❌ 광고 수집 에러: {e}")
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        if driver:
            time.sleep(1)
            driver.quit()
            print("🔒 [광고수집] 브라우저 종료")

def fetch_receiving_data(user_id: str, user_pw: str, days_back: int = 1) -> Dict:
    """
    쿠팡 로켓 supplier에서 입고 데이터를 수집합니다.
    https://supplier.coupang.com/scm/receive/detail 직접 접근
    날짜 컬럼을 파싱하여 날짜별로 그룹핑하여 반환합니다.

    Args:
        days_back: 며칠 전부터 수집할지 (기본 1 = 어제~오늘, catch-up 시 더 큰 값)

    테이블 컬럼 구조 (0-indexed):
      0:구분 | 1:번호 | 2:SKU번호 | 3:SKU명 | 4:입고/반출일자 | 5:물류센터
      6:세금타입 | 7:수량 | 8:단가 | 9:공급가액 | 10:세액 | 11:총단가
      12:총공급가액 | 13:총세액 | 14:계산서번호 | 15:지급일
    """
    driver = None
    try:
        print("🚀 [입고조회 1단계] 브라우저 실행 중...")
        driver = create_chrome_driver(headless=False)
        # 주의: page_load_timeout/script_timeout 설정하지 않음
        # Keycloak 리다이렉트 체인이 길어서 타임아웃 나면 로그인 실패함

        # supplier.coupang.com 접속 및 로그인 (Keycloak 리다이렉트 대기)
        driver.get("https://supplier.coupang.com/")
        time.sleep(3)

        print("🔐 [입고조회 2단계] 로그인 시도 중...")
        print(f"📌 로그인 페이지 URL: {driver.current_url}")

        # 정산(fetch_deduction_data)과 동일한 방식으로 로그인
        do_login(driver, user_id, user_pw, label="[입고]")
        time.sleep(7)
        current_url = driver.current_url
        print(f"📌 로그인 후 URL: {current_url}")

        # 로그인 성공 여부 확인 (정보 로깅용, 실패해도 페이지 이동 시도)
        if "auth" in current_url or "login" in current_url:
            print("⚠️ [입고] 아직 로그인 페이지에 있음 → 추가 대기 후 재시도")
            time.sleep(5)
            # 한 번 더 로그인 시도
            try:
                do_login(driver, user_id, user_pw, label="[입고 재시도]")
                time.sleep(7)
                print(f"📌 재시도 후 URL: {driver.current_url}")
            except Exception as retry_err:
                print(f"⚠️ 재시도 로그인 실패: {retry_err}")

        # 입고상세내역 페이지 직접 이동
        print("📋 [입고조회 3단계] 입고상세내역 페이지 이동...")
        driver.get("https://supplier.coupang.com/scm/receive/detail")
        time.sleep(5)
        print(f"📌 현재 URL: {driver.current_url}")

        # 로그인이 안 되어 auth 페이지로 리다이렉트됐는지 확인
        if "auth" in driver.current_url or "login" in driver.current_url:
            print("❌ [입고] 로그인 실패 - 입고 페이지에 접근할 수 없음")
            return {
                "success": False,
                "error": "입고 페이지 로그인 실패 (로그인 페이지로 리다이렉트됨)",
                "data": [],
                "data_by_date": {},
                "count": 0
            }

        # 날짜 범위 설정 (days_back일 전 ~ 오늘)
        from datetime import datetime, timedelta
        start_dt = datetime.now() - timedelta(days=days_back)
        today_dt = datetime.now()
        print(f"📅 [입고조회 4단계] 날짜 범위: {start_dt.strftime('%Y-%m-%d')} ~ {today_dt.strftime('%Y-%m-%d')}")

        date_set_ok = False
        try:
            # 방법 1: 기간 버튼 클릭 (가장 확실)
            period_buttons = ['1주일', '일주일', '7일', '1주'] if days_back <= 7 else ['1개월', '한달', '30일', '1주일']
            for text in period_buttons:
                btns = driver.find_elements(By.XPATH, f"//*[text()='{text}']")
                for btn in btns:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        print(f"📌 '{text}' 기간 버튼 클릭!")
                        time.sleep(3)
                        date_set_ok = True
                        break
                if date_set_ok:
                    break

            # 방법 2: 날짜 입력 필드 직접 변경
            if not date_set_ok:
                print("📌 기간 버튼 없음 → 날짜 입력 필드 직접 변경")
                all_inputs = driver.find_elements(By.TAG_NAME, "input")
                date_inputs = []
                for inp in all_inputs:
                    val = (inp.get_attribute('value') or '').strip()
                    inp_type = (inp.get_attribute('type') or '').lower()
                    if re.match(r'\d{4}[.\-]\d{2}[.\-]\d{2}', val):
                        date_inputs.append((inp, val))
                    elif inp_type == 'date':
                        date_inputs.append((inp, val))

                print(f"📌 날짜 입력 필드 {len(date_inputs)}개 발견: {[v for _, v in date_inputs]}")

                if len(date_inputs) >= 1:
                    start_inp, start_val = date_inputs[0]
                    sep = '.' if '.' in start_val else '-'
                    new_start = start_dt.strftime(f'%Y{sep}%m{sep}%d')

                    # JS로 값 설정 + 모든 이벤트 발생
                    driver.execute_script("""
                        var el = arguments[0], newVal = arguments[1];
                        el.focus();
                        var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        nativeSetter.call(el, newVal);
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                        el.dispatchEvent(new Event('blur', {bubbles: true}));
                    """, start_inp, new_start)
                    time.sleep(1)

                    after_val = (start_inp.get_attribute('value') or '').strip()
                    print(f"📌 시작일 변경: {start_val} → {after_val}")

                    if after_val == new_start:
                        date_set_ok = True
                    else:
                        # 폴백: send_keys
                        print("📌 JS 변경 실패 → send_keys 시도")
                        start_inp.click()
                        time.sleep(0.3)
                        start_inp.send_keys(Keys.COMMAND + "a" if os.name != 'nt' else Keys.CONTROL + "a")
                        time.sleep(0.2)
                        start_inp.send_keys(Keys.BACKSPACE)
                        time.sleep(0.2)
                        for ch in new_start:
                            start_inp.send_keys(ch)
                            time.sleep(0.05)
                        start_inp.send_keys(Keys.TAB)
                        time.sleep(1)
                        after_val2 = (start_inp.get_attribute('value') or '').strip()
                        print(f"📌 시작일 변경 (send_keys): → {after_val2}")
                        if after_val2 == new_start:
                            date_set_ok = True
                else:
                    print(f"⚠️ 날짜 입력 필드를 찾지 못함")
        except Exception as e:
            print(f"⚠️ 날짜 범위 설정 실패: {e}")

        if not date_set_ok:
            print("⚠️ 날짜 변경 실패 → 페이지 기본 날짜로 조회됩니다")

        # 검색 버튼 클릭
        try:
            search_btns = driver.find_elements(By.XPATH, "//button[contains(text(), '검색')]")
            if search_btns:
                driver.execute_script("arguments[0].click();", search_btns[0])
                print("🔍 검색 버튼 클릭!")
                time.sleep(5)
            else:
                print("⚠️ 검색 버튼을 찾지 못함")
        except Exception as e:
            print(f"⚠️ 검색 버튼 클릭 실패: {e}")

        # 테이블 데이터 수집
        print("📊 [입고조회 5단계] 입고 데이터 수집 중...")
        time.sleep(3)

        receiving_data = {}  # {날짜: {SKU명: 합산수량}}
        today_fallback = today_dt.strftime('%Y-%m-%d')

        try:
            table_rows = driver.find_elements(By.XPATH, "//table//tbody//tr")
            if not table_rows:
                table_rows = driver.find_elements(By.XPATH, "//table//tr")
            print(f"📋 테이블 행 수: {len(table_rows)}")

            # 헤더 기반 컬럼 인덱스 탐지
            col_sku = 3   # SKU 명 기본 인덱스
            col_qty = 7   # 수량 기본 인덱스
            col_date = 4  # 입고/반출일자 기본 인덱스

            header_rows = driver.find_elements(By.XPATH, "//table//thead//tr | //table//tr[th]")
            if header_rows:
                headers = header_rows[0].find_elements(By.TAG_NAME, "th")
                header_texts = [h.text.strip() for h in headers]
                print(f"📋 테이블 헤더: {header_texts}")

                for idx, h in enumerate(header_texts):
                    if 'SKU 명' in h or 'SKU명' in h:
                        col_sku = idx
                    if h == '수량':
                        col_qty = idx
                    if '일자' in h:
                        col_date = idx

                print(f"📋 컬럼 인덱스 - SKU명: {col_sku}, 수량: {col_qty}, 일자: {col_date}")

            for row in table_rows:
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) <= max(col_sku, col_qty):
                        continue

                    sku_name = cells[col_sku].text.strip()
                    qty_text = cells[col_qty].text.strip().replace(',', '')

                    if not sku_name or len(sku_name) < 2:
                        continue

                    quantity = int(qty_text) if qty_text.isdigit() else 0
                    if quantity <= 0:
                        continue

                    # 날짜 파싱 (YYYY.MM.DD 또는 YYYY-MM-DD → YYYY-MM-DD)
                    row_date = today_fallback
                    if len(cells) > col_date:
                        date_text = cells[col_date].text.strip()
                        normalized = date_text.replace('.', '-').replace('/', '-')[:10]
                        if re.match(r'\d{4}-\d{2}-\d{2}', normalized):
                            row_date = normalized

                    if row_date not in receiving_data:
                        receiving_data[row_date] = {}
                    receiving_data[row_date][sku_name] = receiving_data[row_date].get(sku_name, 0) + quantity
                    print(f"✅ [{row_date}] {sku_name} → 수량 {quantity}")

                except Exception:
                    continue

            # 데이터 없을 때 체크
            if not receiving_data:
                body_text = driver.find_element(By.TAG_NAME, "body").text
                if "결과가 없습니다" in body_text or "데이터가 없습니다" in body_text or "검색 건수\n0" in body_text:
                    print("ℹ️ 입고 데이터가 없습니다.")
                    return {
                        "success": True,
                        "data": [],
                        "data_by_date": {},
                        "count": 0,
                        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                        "message": "입고 데이터 없음"
                    }
                print(f"⚠️ 테이블 파싱 실패. 페이지 텍스트 일부: {body_text[:500]}")

        except Exception as e:
            print(f"⚠️ 데이터 수집 중 오류: {e}")

        total_skus = sum(len(v) for v in receiving_data.values())
        print(f"\n🎊 입고 조회 완료! {len(receiving_data)}일 × {total_skus}개 SKU 수집")

        # 기존 호환 리스트 + 날짜별 그룹 데이터 모두 반환
        receiving_list = []
        for date_str, items in receiving_data.items():
            for sku, qty in items.items():
                receiving_list.append({"sku_name": sku, "quantity": qty, "date": date_str})

        return {
            "success": True,
            "data": receiving_list,
            "data_by_date": receiving_data,
            "count": len(receiving_list),
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
        }

    except Exception as e:
        print(f"❌ 입고 조회 에러: {e}")
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        if driver:
            time.sleep(2)
            driver.quit()
            print("🔒 브라우저 종료")



if __name__ == "__main__":
    # 테스트용 실행
    result = fetch_stock_data("test_id", "test_pw")
    print(result)





def fetch_settlement_data(user_id: str, user_pw: str) -> Dict:
    """
    쿠팡 로켓 supplier에서 정산 데이터를 수집합니다.
    https://supplier.coupang.com/ → 물류 → 입고상세내역
    SKU명, 총단가, 지급일 정보를 날짜별로 수집합니다.
    
    Args:
        user_id: 쿠팡 사용자 ID
        user_pw: 쿠팡 사용자 비밀번호
    
    Returns:
        Dict: 성공 시 정산 데이터 리스트, 실패 시 에러 메시지
    """
    driver = None
    try:
        print("🚀 [정산조회 1단계] 브라우저 실행 중...")
        driver = create_chrome_driver(headless=HEADLESS_MODE)

        # supplier.coupang.com 접속
        driver.get("https://supplier.coupang.com/")
        time.sleep(5)

        # 1. 로그인 단계
        print("🔐 [정산조회 2단계] 로그인 시도 중...")
        do_login(driver, user_id, user_pw, label="[정산]")
        
        time.sleep(7)

        # 2. 물류 메뉴 클릭
        print("📦 [정산조회 3단계] 물류 메뉴 탐색 중...")
        try:
            logistics_menu = driver.find_elements(By.XPATH, "//*[contains(text(), '물류')]")
            if logistics_menu:
                driver.execute_script("arguments[0].click();", logistics_menu[0])
                print("📌 물류 메뉴 클릭!")
                time.sleep(2)
        except Exception as e:
            print(f"⚠️ 물류 메뉴 클릭 오류: {e}")

        # 3. 입고상세내역 클릭
        print("📋 [정산조회 4단계] 입고상세내역 메뉴 클릭...")
        try:
            receiving_menu = driver.find_elements(By.XPATH, "//*[contains(text(), '입고상세내역') or contains(text(), '입고 상세내역')]")
            if receiving_menu:
                driver.execute_script("arguments[0].click();", receiving_menu[0])
                print("📌 입고상세내역 클릭!")
                time.sleep(5)
            else:
                driver.get("https://supplier.coupang.com/wms/receiving-detail")
                time.sleep(5)
        except Exception as e:
            print(f"⚠️ 입고상세내역 클릭 오류: {e}")

        # 4. 테이블에서 정산 데이터 수집 (SKU명, 총단가, 지급일)
        print("💰 [정산조회 5단계] 정산 데이터 수집 중...")
        time.sleep(3)
        
        settlement_data = []  # [{sku_name, amount, payment_date}]
        
        try:
            table_rows = driver.find_elements(By.XPATH, "//table//tr")
            print(f"📊 테이블 행 수: {len(table_rows)}")
            
            for row in table_rows:
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 5:
                        row_data = [cell.text.strip() for cell in cells]
                        
                        # 각 셀에서 SKU명, 총단가, 지급일 찾기
                        sku_name = ""
                        amount = 0
                        payment_date = ""
                        
                        for i, cell_text in enumerate(row_data):
                            # SKU명 (긴 텍스트)
                            if len(cell_text) > 10 and not cell_text.replace(',', '').replace('-', '').isdigit():
                                if not sku_name:
                                    sku_name = cell_text
                            
                            # 금액 (숫자 + 콤마)
                            clean_text = cell_text.replace(',', '').replace('원', '').strip()
                            if clean_text.isdigit() and int(clean_text) > 100:
                                amount = int(clean_text)
                            
                            # 날짜 형식 (YYYY-MM-DD 또는 YYYY.MM.DD)
                            if '-' in cell_text or '.' in cell_text:
                                parts = cell_text.replace('.', '-').split('-')
                                if len(parts) == 3 and all(p.isdigit() for p in parts):
                                    payment_date = cell_text.replace('.', '-')
                        
                        if sku_name and amount > 0 and payment_date:
                            settlement_data.append({
                                "sku_name": sku_name,
                                "amount": amount,
                                "payment_date": payment_date,
                                "type": "매출"
                            })
                            
                except Exception:
                    continue
                    
        except Exception as e:
            print(f"⚠️ 데이터 수집 중 오류: {e}")

        print(f"\n💰 정산 조회 완료! {len(settlement_data)}개 항목 수집")
        
        return {
            "success": True,
            "data": settlement_data,
            "count": len(settlement_data),
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
        }

    except Exception as e:
        print(f"❌ 정산 조회 에러: {e}")
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        if driver:
            time.sleep(2)
            driver.quit()
            print("🔒 브라우저 종료")


def fetch_deduction_data(user_id: str, user_pw: str, start_year: int = 2025, start_month: int = 11) -> Dict:
    """
    쿠팡 supplier에서 공제금액계정 데이터를 수집합니다.
    정산 → 공제금액계정 메뉴에서 월별로 데이터를 조회합니다.
    
    Args:
        user_id: 쿠팡 사용자 ID
        user_pw: 쿠팡 사용자 비밀번호
        start_year: 시작 연도 (기본값: 2025)
        start_month: 시작 월 (기본값: 11)
    
    Returns:
        Dict: 성공 시 공제금액 데이터 리스트, 실패 시 에러 메시지
    """
    driver = None
    logs = []  # 디버그 로그 수집
    def log(msg):
        print(msg)
        logs.append(msg)

    try:
        log("🚀 [1단계] 브라우저 실행 중...")
        driver = create_chrome_driver(headless=False)

        # supplier.coupang.com 접속
        driver.get("https://supplier.coupang.com/")
        time.sleep(3)
        log(f"📌 접속 후 URL: {driver.current_url}")

        # 1. 로그인 단계
        log("🔐 [2단계] 로그인 시도 중...")
        do_login(driver, user_id, user_pw, label="[정산-버퍼]")

        time.sleep(7)
        log(f"📌 로그인 후 URL: {driver.current_url}")

        # 2. 공제금액계정 페이지로 직접 이동 (메뉴 클릭 대신 URL 직접 접근)
        print("💰 [공제금액 3단계] 공제금액계정 페이지로 직접 이동...")
        try:
            # 직접 URL로 이동 (가장 확실한 방법)
            driver.get("https://supplier.coupang.com/scm/settlement/deductible/amount/account?searchType=PAYMENT")
            time.sleep(5)
            print(f"📌 현재 URL: {driver.current_url}")
            
            # 페이지 로딩 확인
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            # 연도 드롭다운이 나타날 때까지 대기 (최대 10초)
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "year"))
                )
                print("✅ 공제금액계정 페이지 로딩 완료!")
            except:
                print("⚠️ 페이지 로딩 대기 타임아웃, 계속 진행...")
                # 혹시 다른 URL일 수 있으니 대체 URL 시도
                driver.get("https://supplier.coupang.com/scm/settlement/deductible/amount/account?searchType=PAYMENT")
                time.sleep(5)
                print(f"📌 대체 URL 시도 후: {driver.current_url}")
                
        except Exception as e:
            print(f"⚠️ 공제금액계정 페이지 이동 오류: {e}")

        # 3. 월별로 데이터 수집
        print("📊 [공제금액 4단계] 월별 데이터 수집 중...")
        
        all_deduction_data = []  # 모든 월의 데이터
        
        # 현재 날짜
        import datetime
        today = datetime.date.today()
        current_year = today.year
        current_month = today.month
        
        # 시작 월부터 현재 월까지 순회
        year = start_year
        month = start_month
        
        while (year < current_year) or (year == current_year and month <= current_month):
            print(f"📅 {year}년 {month}월 데이터 조회 중...")
            
            try:
                # 연도 드롭다운 선택
                from selenium.webdriver.support.ui import Select
                
                # 연도 드롭다운 찾기 (정확한 id 사용)
                year_select_elem = driver.find_element(By.ID, "year")
                if year_select_elem:
                    year_select = Select(year_select_elem)
                    # 연도 값으로 선택 시도
                    try:
                        year_select.select_by_value(str(year))
                        print(f"   📅 연도 선택 (by value): {year}")
                    except:
                        try:
                            year_select.select_by_visible_text(f"{year}년")
                            print(f"   📅 연도 선택 (by text): {year}년")
                        except:
                            year_select.select_by_visible_text(str(year))
                            print(f"   📅 연도 선택 (by text2): {year}")
                else:
                    print(f"   ⚠️ 연도 드롭다운을 찾을 수 없음")
                
                time.sleep(0.5)
                
                # 월 드롭다운 찾기 (정확한 id 사용)
                month_select_elem = driver.find_element(By.ID, "month")
                if month_select_elem:
                    month_select = Select(month_select_elem)
                    # 월 값으로 선택 시도
                    try:
                        month_select.select_by_value(str(month))
                        print(f"   📅 월 선택 (by value): {month}")
                    except:
                        try:
                            month_select.select_by_visible_text(f"{month}월")
                            print(f"   📅 월 선택 (by text): {month}월")
                        except:
                            month_select.select_by_visible_text(str(month))
                            print(f"   📅 월 선택 (by text2): {month}")
                else:
                    print(f"   ⚠️ 월 드롭다운을 찾을 수 없음")
                
                time.sleep(1)
                
                # 검색 버튼 클릭
                search_btn = driver.find_elements(By.XPATH, "//button[contains(text(), '검색')]")
                if not search_btn:
                    search_btn = driver.find_elements(By.XPATH, "//button[@type='submit' or @type='button']")
                if not search_btn:
                    search_btn = driver.find_elements(By.XPATH, "//*[contains(@class, 'btn') and contains(text(), '검색')]")
                
                if search_btn:
                    driver.execute_script("arguments[0].click();", search_btn[0])
                    print(f"   🔍 검색 버튼 클릭")
                    time.sleep(3)

                # 검색 후 1페이지로 명시적 이동 (이전 달 마지막 페이지가 남아있을 수 있음)
                try:
                    page1_btns = driver.find_elements(By.XPATH, "//*[contains(@class, 'pagination')]//button[text()='1'] | //*[contains(@class, 'pagination')]//a[text()='1'] | //nav//button[text()='1'] | //nav//a[text()='1']")
                    if page1_btns:
                        driver.execute_script("arguments[0].click();", page1_btns[0])
                        time.sleep(2)
                        print(f"   📄 1페이지로 이동")
                except Exception:
                    pass

                # 페이지네이션 처리 - 최대 페이지 숫자 찾기
                total_rows_collected = 0

                # 먼저 최대 페이지 번호 확인
                max_page = 1
                try:
                    page_btns = driver.find_elements(By.XPATH, "//*[contains(@class, 'pagination')]//button | //*[contains(@class, 'pagination')]//a | //nav//button | //nav//a")
                    for btn in page_btns:
                        btn_text = btn.text.strip()
                        if btn_text.isdigit():
                            page_num = int(btn_text)
                            if page_num > max_page:
                                max_page = page_num
                    print(f"   📊 총 {max_page}페이지 발견")
                except Exception as e:
                    print(f"   ⚠️ 페이지 탐색 오류: {e}")

                # 각 페이지 순회
                for current_page in range(1, max_page + 1):
                    # 페이지 버튼 클릭 (1페이지가 아닌 경우)
                    if current_page > 1:
                        try:
                            page_btns = driver.find_elements(By.XPATH, f"//*[contains(@class, 'pagination')]//button[text()='{current_page}'] | //*[contains(@class, 'pagination')]//a[text()='{current_page}'] | //nav//button[text()='{current_page}'] | //nav//a[text()='{current_page}']")
                            if page_btns:
                                driver.execute_script("arguments[0].click();", page_btns[0])
                                time.sleep(2)
                        except Exception as e:
                            print(f"   ⚠️ 페이지 {current_page} 클릭 실패: {e}")
                            continue
                    
                    # 테이블 데이터 수집
                    table_rows = driver.find_elements(By.XPATH, "//table//tr")
                    
                    # 헤더 추출 (첫 페이지에서만)
                    if current_page == 1:
                        headers = []
                        if table_rows:
                            header_cells = table_rows[0].find_elements(By.TAG_NAME, "th")
                            headers = [cell.text.strip() for cell in header_cells]
                            # 마지막 열(상세내역) 제외
                            if headers and ('상세' in headers[-1] or '내역' in headers[-1]):
                                headers = headers[:-1]
                    
                    # 데이터 행 추출
                    rows_in_page = 0
                    for row in table_rows[1:]:  # 헤더 제외
                        cells = row.find_elements(By.TAG_NAME, "td")
                        if len(cells) >= 2:
                            row_data = {}
                            for i, cell in enumerate(cells[:-1]):  # 마지막 열(상세내역) 제외
                                if i < len(headers):
                                    row_data[headers[i]] = cell.text.strip()
                                else:
                                    row_data[f"col_{i}"] = cell.text.strip()
                            
                            # 조회 월 정보 추가
                            row_data["_query_month"] = f"{year}-{str(month).zfill(2)}"
                            
                            if row_data:
                                all_deduction_data.append(row_data)
                                rows_in_page += 1
                    
                    total_rows_collected += rows_in_page
                    print(f"   📄 페이지 {current_page}/{max_page}: {rows_in_page}개 행 수집")
                
                print(f"   → 총 {total_rows_collected}개 행 수집 완료")
                
            except Exception as e:
                print(f"⚠️ {year}년 {month}월 데이터 수집 오류: {e}")
            
            # 다음 월로 이동
            month += 1
            if month > 12:
                month = 1
                year += 1
            
            time.sleep(1)

        log(f"\n📊 공제금액 조회 완료! 총 {len(all_deduction_data)}개 항목 수집")

        return {
            "success": True,
            "data": all_deduction_data,
            "count": len(all_deduction_data),
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "message": " | ".join(logs)
        }

    except Exception as e:
        log(f"❌ 공제금액 조회 에러: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": " | ".join(logs)
        }
    finally:
        if driver:
            time.sleep(2)
            driver.quit()
            print("🔒 브라우저 종료")


def fetch_supplier_combined(user_id: str, user_pw: str, days_back: int = 1,
                            start_year: int = 2025, start_month: int = 11) -> Dict:
    """
    supplier.coupang.com에 한 번 로그인 → 입고 + 정산 모두 수집.
    fetch_deduction_data(작동함)와 동일한 브라우저/로그인 방식.
    """
    driver = None
    try:
        print("🚀 [공급자통합] 브라우저 실행...", flush=True)
        driver = create_chrome_driver(headless=False)

        driver.get("https://supplier.coupang.com/")
        time.sleep(3)
        print(f"📌 접속: {driver.current_url}", flush=True)

        print("🔐 [공급자통합] 로그인...", flush=True)
        do_login(driver, user_id, user_pw, label="[공급자통합]")
        time.sleep(7)
        print(f"📌 로그인 후: {driver.current_url}", flush=True)

        receiving_result = _collect_receiving(driver, days_back)
        time.sleep(2)
        deduction_result = _collect_deduction(driver, start_year, start_month)

        return {"receiving": receiving_result, "deduction": deduction_result}
    except Exception as e:
        print(f"❌ 공급자통합 에러: {e}", flush=True)
        return {
            "receiving": {"success": False, "error": str(e), "data": [], "data_by_date": {}, "count": 0},
            "deduction": {"success": False, "error": str(e), "data": [], "count": 0}
        }
    finally:
        if driver:
            time.sleep(2)
            driver.quit()
            print("🔒 [공급자통합] 브라우저 종료", flush=True)


def _collect_receiving(driver, days_back: int = 1) -> Dict:
    """이미 로그인된 driver로 입고 데이터 수집"""
    from datetime import datetime, timedelta
    try:
        print("📋 [입고] 페이지 이동...", flush=True)
        driver.get("https://supplier.coupang.com/scm/receive/detail")
        time.sleep(5)
        print(f"📌 [입고] URL: {driver.current_url}", flush=True)

        if "auth" in driver.current_url or "login" in driver.current_url:
            print("❌ [입고] 세션 없음", flush=True)
            return {"success": False, "error": "세션 없음", "data": [], "data_by_date": {}, "count": 0}

        start_dt = datetime.now() - timedelta(days=days_back)
        today_dt = datetime.now()
        print(f"📅 [입고] {start_dt.strftime('%Y-%m-%d')} ~ {today_dt.strftime('%Y-%m-%d')}", flush=True)

        date_set_ok = False
        try:
            # 방법 1: 기간 버튼 클릭 (가장 확실)
            period_buttons = ['1주일', '일주일', '7일', '1주'] if days_back <= 7 else ['1개월', '한달', '30일', '1주일']
            for text in period_buttons:
                btns = driver.find_elements(By.XPATH, f"//*[text()='{text}']")
                for btn in btns:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        print(f"📌 [입고] '{text}' 기간 버튼 클릭!", flush=True)
                        time.sleep(3)
                        date_set_ok = True
                        break
                if date_set_ok:
                    break

            # 방법 2: 날짜 입력 필드 직접 변경
            if not date_set_ok:
                print("📌 [입고] 기간 버튼 없음 → 날짜 입력 직접 변경", flush=True)
                date_inputs = []
                for inp in driver.find_elements(By.TAG_NAME, "input"):
                    val = (inp.get_attribute('value') or '').strip()
                    if re.match(r'\d{4}[.\-]\d{2}[.\-]\d{2}', val):
                        date_inputs.append((inp, val))
                    elif (inp.get_attribute('type') or '').lower() == 'date':
                        date_inputs.append((inp, val))
                print(f"📌 [입고] 날짜필드 {len(date_inputs)}개: {[v for _,v in date_inputs]}", flush=True)

                if date_inputs:
                    si, sv = date_inputs[0]
                    sep = '.' if '.' in sv else '-'
                    nv = start_dt.strftime(f'%Y{sep}%m{sep}%d')
                    driver.execute_script("""
                        var el=arguments[0],v=arguments[1];
                        el.focus();
                        var s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
                        s.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}));
                        el.dispatchEvent(new Event('change',{bubbles:true}));
                        el.dispatchEvent(new Event('blur',{bubbles:true}));
                    """, si, nv)
                    time.sleep(1)
                    av = (si.get_attribute('value') or '').strip()
                    print(f"📌 [입고] 시작일: {sv} → {av}", flush=True)
                    if av == nv:
                        date_set_ok = True
                    else:
                        si.click(); time.sleep(0.3)
                        si.send_keys(Keys.COMMAND+"a" if os.name!='nt' else Keys.CONTROL+"a")
                        time.sleep(0.2); si.send_keys(Keys.BACKSPACE); time.sleep(0.2)
                        for ch in nv:
                            si.send_keys(ch); time.sleep(0.05)
                        si.send_keys(Keys.TAB); time.sleep(1)
                        av2 = (si.get_attribute('value') or '').strip()
                        print(f"📌 [입고] 시작일 (send_keys): → {av2}", flush=True)
                        if av2 == nv: date_set_ok = True
        except Exception as e:
            print(f"⚠️ [입고] 날짜설정 실패: {e}", flush=True)

        if not date_set_ok:
            print("⚠️ [입고] 날짜 변경 실패 → 페이지 기본 날짜로 조회", flush=True)

        try:
            sbs = driver.find_elements(By.XPATH, "//button[contains(text(),'검색')]")
            if sbs:
                driver.execute_script("arguments[0].click();", sbs[0])
                print("🔍 [입고] 검색!", flush=True)
                time.sleep(5)
            else:
                print("⚠️ [입고] 검색 버튼 없음", flush=True)
        except Exception as e:
            print(f"⚠️ [입고] 검색 실패: {e}", flush=True)

        print("📊 [입고] 테이블 수집...", flush=True)
        time.sleep(3)

        receiving_data = {}
        today_fallback = today_dt.strftime('%Y-%m-%d')

        trs = driver.find_elements(By.XPATH, "//table//tbody//tr")
        if not trs: trs = driver.find_elements(By.XPATH, "//table//tr")
        print(f"📋 [입고] 행: {len(trs)}", flush=True)

        cs, cq, cd = 3, 7, 4
        hrs = driver.find_elements(By.XPATH, "//table//thead//tr|//table//tr[th]")
        if hrs:
            ht = [h.text.strip() for h in hrs[0].find_elements(By.TAG_NAME, "th")]
            print(f"📋 [입고] 헤더: {ht}", flush=True)
            for i, h in enumerate(ht):
                if 'SKU 명' in h or 'SKU명' in h: cs = i
                if h == '수량': cq = i
                if '일자' in h: cd = i

        for row in trs:
            try:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) <= max(cs, cq): continue
                sn = cells[cs].text.strip()
                qt = cells[cq].text.strip().replace(',', '')
                if not sn or len(sn) < 2: continue
                q = int(qt) if qt.isdigit() else 0
                if q <= 0: continue
                rd = today_fallback
                if len(cells) > cd:
                    dt = cells[cd].text.strip().replace('.', '-').replace('/', '-')[:10]
                    if re.match(r'\d{4}-\d{2}-\d{2}', dt): rd = dt
                if rd not in receiving_data: receiving_data[rd] = {}
                receiving_data[rd][sn] = receiving_data[rd].get(sn, 0) + q
                print(f"✅ [입고] [{rd}] {sn} → {q}", flush=True)
            except: continue

        if not receiving_data:
            bt = driver.find_element(By.TAG_NAME, "body").text
            if any(k in bt for k in ["결과가 없습니다", "데이터가 없습니다", "검색 건수\n0"]):
                print("ℹ️ [입고] 데이터 없음", flush=True)
            else:
                print(f"⚠️ [입고] 파싱실패: {bt[:300]}", flush=True)

        ts = sum(len(v) for v in receiving_data.values())
        print(f"🎊 [입고] {len(receiving_data)}일 × {ts}SKU", flush=True)

        rl = []
        for ds, items in receiving_data.items():
            for sku, qty in items.items():
                rl.append({"sku_name": sku, "quantity": qty, "date": ds})
        return {"success": True, "data": rl, "data_by_date": receiving_data,
                "count": len(rl), "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')}
    except Exception as e:
        print(f"❌ [입고] 에러: {e}", flush=True)
        return {"success": False, "error": str(e), "data": [], "data_by_date": {}, "count": 0}


def _collect_deduction(driver, start_year: int = 2025, start_month: int = 11) -> Dict:
    """이미 로그인된 driver로 정산 데이터 수집"""
    import datetime as dt_module
    from selenium.webdriver.support.ui import Select
    logs = []
    def log(msg):
        print(msg, flush=True)
        logs.append(msg)

    try:
        log("💰 [정산] 페이지 이동...")
        driver.get("https://supplier.coupang.com/scm/settlement/deductible/amount/account?searchType=PAYMENT")
        time.sleep(5)
        log(f"📌 [정산] URL: {driver.current_url}")

        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "year")))
            log("✅ [정산] 로딩 완료")
        except:
            log("⚠️ [정산] 타임아웃, 재시도...")
            driver.get("https://supplier.coupang.com/scm/settlement/deductible/amount/account?searchType=PAYMENT")
            time.sleep(5)

        all_data = []
        today = dt_module.date.today()
        cy, cm = today.year, today.month
        year, month = start_year, start_month

        while (year < cy) or (year == cy and month <= cm):
            log(f"📅 [정산] {year}년 {month}월...")
            try:
                ys = Select(driver.find_element(By.ID, "year"))
                try: ys.select_by_value(str(year))
                except:
                    try: ys.select_by_visible_text(f"{year}년")
                    except: ys.select_by_visible_text(str(year))
                time.sleep(0.5)

                ms = Select(driver.find_element(By.ID, "month"))
                try: ms.select_by_value(str(month))
                except:
                    try: ms.select_by_visible_text(f"{month}월")
                    except: ms.select_by_visible_text(str(month))
                time.sleep(1)

                sb = driver.find_elements(By.XPATH, "//button[contains(text(),'검색')]")
                if not sb: sb = driver.find_elements(By.XPATH, "//button[@type='submit' or @type='button']")
                if sb: driver.execute_script("arguments[0].click();", sb[0]); time.sleep(3)

                try:
                    p1 = driver.find_elements(By.XPATH, "//*[contains(@class,'pagination')]//button[text()='1']|//*[contains(@class,'pagination')]//a[text()='1']|//nav//button[text()='1']|//nav//a[text()='1']")
                    if p1: driver.execute_script("arguments[0].click();", p1[0]); time.sleep(2)
                except: pass

                mp = 1
                try:
                    for b in driver.find_elements(By.XPATH, "//*[contains(@class,'pagination')]//button|//*[contains(@class,'pagination')]//a|//nav//button|//nav//a"):
                        t = b.text.strip()
                        if t.isdigit() and int(t) > mp: mp = int(t)
                except: pass

                tr_total = 0
                for cp in range(1, mp + 1):
                    if cp > 1:
                        try:
                            pb = driver.find_elements(By.XPATH, f"//*[contains(@class,'pagination')]//button[text()='{cp}']|//*[contains(@class,'pagination')]//a[text()='{cp}']|//nav//button[text()='{cp}']|//nav//a[text()='{cp}']")
                            if pb: driver.execute_script("arguments[0].click();", pb[0]); time.sleep(2)
                        except: continue

                    trs = driver.find_elements(By.XPATH, "//table//tr")
                    if cp == 1:
                        headers = []
                        if trs:
                            hc = trs[0].find_elements(By.TAG_NAME, "th")
                            headers = [c.text.strip() for c in hc]
                            if headers and ('상세' in headers[-1] or '내역' in headers[-1]):
                                headers = headers[:-1]

                    rip = 0
                    for row in trs[1:]:
                        cells = row.find_elements(By.TAG_NAME, "td")
                        if len(cells) >= 2:
                            rd = {}
                            for i, c in enumerate(cells[:-1]):
                                if i < len(headers): rd[headers[i]] = c.text.strip()
                                else: rd[f"col_{i}"] = c.text.strip()
                            rd["_query_month"] = f"{year}-{str(month).zfill(2)}"
                            if rd: all_data.append(rd); rip += 1
                    tr_total += rip
                    log(f"   📄 [정산] {cp}/{mp}p: {rip}행")
                log(f"   → {tr_total}행")
            except Exception as e:
                log(f"⚠️ [정산] {year}년 {month}월 오류: {e}")

            month += 1
            if month > 12: month = 1; year += 1
            time.sleep(1)

        log(f"📊 [정산] 총 {len(all_data)}개")
        return {"success": True, "data": all_data, "count": len(all_data),
                "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'), "message": " | ".join(logs)}
    except Exception as e:
        log(f"❌ [정산] 에러: {e}")
        return {"success": False, "error": str(e), "data": [], "count": 0, "message": " | ".join(logs)}

