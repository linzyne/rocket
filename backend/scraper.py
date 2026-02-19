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
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from typing import List, Dict, Optional, Union

# 환경변수 기반 headless 모드 (배포 환경에서는 항상 headless)
HEADLESS_MODE = os.getenv("HEADLESS_MODE", "true").lower() == "true"


def do_login(driver, user_id, user_pw, label=""):
    """
    공통 로그인 함수: JS로 값 설정 + 이벤트 디스패치 (봇 감지 우회)
    """
    try:
        pw_field = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']"))
        )
        id_field = driver.find_element(By.CSS_SELECTOR, "input[type='text'], input[type='email']")

        # JS로 값 설정 + React/Vue 이벤트 트리거
        driver.execute_script("""
            var idField = arguments[0];
            var pwField = arguments[1];
            var userId = arguments[2];
            var userPw = arguments[3];

            // 네이티브 setter로 값 설정 (React 호환)
            var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;

            nativeInputValueSetter.call(idField, userId);
            idField.dispatchEvent(new Event('input', { bubbles: true }));
            idField.dispatchEvent(new Event('change', { bubbles: true }));

            nativeInputValueSetter.call(pwField, userPw);
            pwField.dispatchEvent(new Event('input', { bubbles: true }));
            pwField.dispatchEvent(new Event('change', { bubbles: true }));
        """, id_field, pw_field, user_id, user_pw)

        time.sleep(0.5)

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
        uc_options = uc.ChromeOptions()
        if HEADLESS_MODE and not debug_mode:
            uc_options.add_argument("--headless=new")
        uc_options.add_argument("--no-sandbox")
        uc_options.add_argument("--disable-dev-shm-usage")

        driver = uc.Chrome(options=uc_options)

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

def fetch_ad_report(driver, target_date='yesterday', debug_mode=True) -> Optional[Dict]:
    """
    현재 로그인된 드라이버 세션을 사용하여 광고 리포트를 수집합니다.
    '광고표준' 대시보드로 이동하여 요약 데이터 및 캠페인별 상세 데이터를 수집합니다.
    """
    try:
        print("📊 [광고리포트] 대시보드 페이지로 이동 중...")
        
        # 1. 사용자 지정 URL로 이동 ('광고표준' 대시보드)
        target_url = "https://advertising.coupang.com/marketing/dashboard/sales"
        print(f"🔗 [광고리포트] 지정된 대시보드 URL로 이동: {target_url}")
        
        driver.get(target_url)
        time.sleep(5)
                
        # 최종 확인
        if "marketing/dashboard" not in driver.current_url:
             print("⚠️ 페이지 이동 실패: 여전히 다른 페이지에 있습니다. 강제 이동 재시도...")
             driver.get(target_url)
             time.sleep(7)

        # 2. 날짜 선택 ('어제' 클릭)
        select_yesterday_date(driver)

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

        # 5. 캠페인별 상세 데이터 수집 (Nested Scraping)
        print("📦 [광고리포트] 캠페인별 상세 데이터 수집 시작 (Nested Scraping)...")
        all_products = []
        
        try:
            # 5-1. 활성 캠페인 탐색 (ON 토글 버튼 기반)
            campaign_targets = [] # {'type': 'url', 'val': url} or {'type': 'click', 'index': i}
            
            # 테이블 데이터가 로드될 때까지 대기
            time.sleep(3)
            
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
                        time.sleep(5)
                        
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
                                time.sleep(5)
                            
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
                                    time.sleep(5)
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

def fetch_ad_report_only(user_id: str, user_pw: str, debug_mode: bool = True) -> Dict:
    """
    광고 리포트 데이터만 독립적으로 수집합니다.
    브라우저 실행 -> 로그인 -> 광고 리포트 수집 -> 종료 과정을 수행합니다.
    """
    driver = None
    try:
        print("🚀 [광고수집 1단계] 브라우저 실행 중...")
        uc_options = uc.ChromeOptions()
        if HEADLESS_MODE and not debug_mode:
            uc_options.add_argument("--headless=new")
        uc_options.add_argument("--no-sandbox")
        uc_options.add_argument("--disable-dev-shm-usage")

        driver = uc.Chrome(options=uc_options)

        driver.get("https://advertising.coupang.com/marketing/campaigns")
        time.sleep(7)

        # 1. 로그인
        print("🔐 [광고수집 2단계] 로그인 시도 중...")
        all_login_btns = driver.find_elements(By.XPATH, "//*[text()='로그인하기']")
        if len(all_login_btns) >= 2:
            driver.execute_script("arguments[0].click();", all_login_btns[1])

        try:
            do_login(driver, user_id, user_pw, label="[광고]")
            
            # 로그인 후 세션 생성 대기 (너무 빠르면 404 발생 가능)
            time.sleep(6)
            
            # 만약 재고 대시보드(기본페이지)로 이동했다면 광고 페이지로 이동
            current_url = driver.current_url
            if "product-dashboard" in current_url or "login" in current_url:
                target_url = "https://advertising.coupang.com/marketing/dashboard/sales"
                print(f"⚡️ [광고수집] 현재 페이지({current_url}) -> 광고 대시보드로 이동: {target_url}")
                driver.get(target_url)
                time.sleep(5)
        except Exception as login_err:
            print(f"⚠️ 로그인 폼 찾기 실패: {login_err}")

        # 2. 광고 리포트 수집
        print("\n📈 [광고수집 3단계] 광고 리포트 데이터 추출...")
        ad_data = fetch_ad_report(driver, debug_mode=debug_mode)
        
        if ad_data:
            return {
                "success": True,
                "data": ad_data,
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
            time.sleep(2)
            driver.quit()
            print("🔒 [광고수집] 브라우저 종료")

def fetch_receiving_data(user_id: str, user_pw: str) -> Dict:
    """
    쿠팡 로켓 supplier에서 오늘의 입고 데이터를 수집합니다.
    https://supplier.coupang.com/ → 물류 → 입고상세내역
    
    Args:
        user_id: 쿠팡 사용자 ID
        user_pw: 쿠팡 사용자 비밀번호
    
    Returns:
        Dict: 성공 시 입고 데이터 (SKU명: 수량), 실패 시 에러 메시지
    """
    driver = None
    try:
        print("🚀 [입고조회 1단계] 브라우저 실행 중...")
        uc_options = uc.ChromeOptions()
        if HEADLESS_MODE:
            uc_options.add_argument("--headless=new")
        uc_options.add_argument("--no-sandbox")
        uc_options.add_argument("--disable-dev-shm-usage")

        driver = uc.Chrome(options=uc_options)

        # supplier.coupang.com 접속
        driver.get("https://supplier.coupang.com/")
        time.sleep(5)

        # 1. 로그인 단계
        print("🔐 [입고조회 2단계] 로그인 시도 중...")
        do_login(driver, user_id, user_pw, label="[입고]")
        
        time.sleep(7)

        # 2. 물류 메뉴 클릭
        print("📦 [입고조회 3단계] 물류 메뉴 탐색 중...")
        try:
            # "물류" 메뉴 찾기
            logistics_menu = driver.find_elements(By.XPATH, "//*[contains(text(), '물류')]")
            if logistics_menu:
                driver.execute_script("arguments[0].click();", logistics_menu[0])
                print("📌 물류 메뉴 클릭!")
                time.sleep(2)
        except Exception as e:
            print(f"⚠️ 물류 메뉴 클릭 오류: {e}")

        # 3. 입고상세내역 클릭
        print("📋 [입고조회 4단계] 입고상세내역 메뉴 클릭...")
        try:
            receiving_menu = driver.find_elements(By.XPATH, "//*[contains(text(), '입고상세내역') or contains(text(), '입고 상세내역')]")
            if receiving_menu:
                driver.execute_script("arguments[0].click();", receiving_menu[0])
                print("📌 입고상세내역 클릭!")
                time.sleep(5)
            else:
                # 링크로 직접 접근 시도
                driver.get("https://supplier.coupang.com/wms/receiving-detail")
                time.sleep(5)
        except Exception as e:
            print(f"⚠️ 입고상세내역 클릭 오류: {e}")

        # 4. 테이블 데이터 수집 (오늘 날짜는 자동으로 설정됨)
        print("📊 [입고조회 5단계] 입고 데이터 수집 중...")
        time.sleep(3)
        
        receiving_data = {}  # SKU명: 합산 수량
        
        try:
            # 테이블 행 찾기
            table_rows = driver.find_elements(By.XPATH, "//table//tr")
            
            for row in table_rows:
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 5:
                        # 두 번째 이미지 기준: SKU 명 (index 3), 수량 (index 7)
                        # 실제 인덱스는 페이지에 따라 다를 수 있음
                        sku_name = ""
                        quantity = 0
                        
                        # SKU 명 찾기 (보통 3~4번째 컬럼)
                        for i, cell in enumerate(cells):
                            cell_text = cell.text.strip()
                            # 수량 찾기 (숫자만 있는 셀 중 적절한 위치)
                            if i >= 3 and i <= 4 and len(cell_text) > 5:
                                sku_name = cell_text
                            if i >= 7 and i <= 8 and cell_text.isdigit():
                                quantity = int(cell_text)
                        
                        if sku_name and quantity > 0:
                            # 같은 SKU명은 수량 합산
                            if sku_name in receiving_data:
                                receiving_data[sku_name] += quantity
                            else:
                                receiving_data[sku_name] = quantity
                except Exception:
                    continue
            
            # 대체 방법: 페이지 텍스트에서 추출
            if not receiving_data:
                print("📄 테이블 파싱 실패, 텍스트 추출 시도...")
                body_text = driver.find_element(By.TAG_NAME, "body").text
                
                # "해당하는 검색조건에 대한 결과가 없습니다" 체크
                if "결과가 없습니다" in body_text or "데이터가 없습니다" in body_text:
                    print("ℹ️ 오늘 입고 데이터가 없습니다.")
                    return {
                        "success": True,
                        "data": {},
                        "count": 0,
                        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                        "message": "오늘 입고 데이터 없음"
                    }
                
                # 텍스트에서 데이터 추출 시도
                lines = body_text.split('\n')
                print(f"📄 페이지 라인 수: {len(lines)}")
                
        except Exception as e:
            print(f"⚠️ 데이터 수집 중 오류: {e}")

        print(f"\n🎊 입고 조회 완료! {len(receiving_data)}개 SKU 수집")
        
        # 리스트 형태로 변환
        receiving_list = [
            {"sku_name": sku, "quantity": qty}
            for sku, qty in receiving_data.items()
        ]
        
        return {
            "success": True,
            "data": receiving_list,
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
        uc_options = uc.ChromeOptions()
        if HEADLESS_MODE:
            uc_options.add_argument("--headless=new")
        uc_options.add_argument("--no-sandbox")
        uc_options.add_argument("--disable-dev-shm-usage")

        driver = uc.Chrome(options=uc_options)

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
        uc_options = uc.ChromeOptions()
        # headless 사용 안 함 (쿠팡 봇 감지 우회)
        uc_options.add_argument("--no-sandbox")
        uc_options.add_argument("--disable-dev-shm-usage")

        driver = uc.Chrome(options=uc_options)

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


