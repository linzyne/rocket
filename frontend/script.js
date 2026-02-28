/**
 * 쿠팡 재고 대시보드 - 피벗 테이블 버전 (입고/재고/판매)
 * 날짜별 입고, 재고, 판매량을 한 달치 한눈에 표시
 */

// ========================================
// 설정
// ========================================
// 수집(크롤링)은 반드시 로컬 백엔드, 조회(캐시)는 Render
const LOCAL_API = 'http://localhost:8000';
const REMOTE_API = 'https://rocket-3tpn.onrender.com';
const API_BASE_URL = LOCAL_API;  // 크롤링용 (로컬 백엔드 필요)
const STORAGE_KEY = 'coupang_stock_history';
const RECEIVING_STORAGE_KEY = 'coupang_receiving_history';
const AD_STORAGE_KEY = 'coupang_ad_history';
const MAPPING_STORAGE_KEY = 'coupang_product_mapping';
const DEDUCTION_STORAGE_KEY = 'coupang_deduction_data';

// 로그인 자격증명 가져오기 (localStorage → 로그인 폼 fallback)
function getCredentials() {
    let userId = localStorage.getItem('coupang_user_id');
    let userPw = localStorage.getItem('coupang_user_pw');
    if (!userId || !userPw) {
        const idInput = document.getElementById('userId');
        const pwInput = document.getElementById('userPw');
        if (idInput && idInput.value.trim()) userId = idInput.value.trim();
        if (pwInput && pwInput.value) userPw = pwInput.value;
        if (userId && userPw) {
            localStorage.setItem('coupang_user_id', userId);
            localStorage.setItem('coupang_user_pw', userPw);
        }
    }
    return { userId, userPw };
}

// ========================================
// DOM 요소
// ========================================
const elements = {
    // 섹션
    loginSection: document.getElementById('loginSection'),
    loadingSection: document.getElementById('loadingSection'),
    resultSection: document.getElementById('resultSection'),
    errorSection: document.getElementById('errorSection'),

    // 폼
    loginForm: document.getElementById('loginForm'),
    userIdInput: document.getElementById('userId'),
    userPwInput: document.getElementById('userPw'),

    // 로딩
    loadingStatus: document.getElementById('loadingStatus'),
    loadingTitle: document.getElementById('loadingTitle'),
    progressFill: document.getElementById('progressFill'),

    // 결과
    periodLabel: document.getElementById('periodLabel'),
    totalItems: document.getElementById('totalItems'),
    recordDays: document.getElementById('recordDays'),
    totalSalesMonth: document.getElementById('totalSalesMonth'),
    pivotTableHead: document.getElementById('pivotTableHead'),
    pivotTableBody: document.getElementById('pivotTableBody'),

    // 버튼
    fetchBtn: document.getElementById('fetchBtn'),
    downloadBtn: document.getElementById('downloadBtn'),
    newFetchBtn: document.getElementById('newFetchBtn'),
    viewHistoryBtn: document.getElementById('viewHistoryBtn'),
    retryBtn: document.getElementById('retryBtn'),
    prevMonthBtn: document.getElementById('prevMonthBtn'),
    nextMonthBtn: document.getElementById('nextMonthBtn'),
    mappingBtn: document.getElementById('mappingBtn'),

    // 기타
    errorMessage: document.getElementById('errorMessage'),
    toastContainer: document.getElementById('toastContainer')
};

// ========================================
// 상태 관리
// ========================================
let stockHistory = {};       // 날짜별 재고 데이터 { "2026-02-08": [{product_name, stock, ad_status}] }
let receivingHistory = {};   // 날짜별 입고 데이터 { "2026-02-08": {"SKU명": 수량} }
let deductionHistory = [];   // 정산내역 데이터 [{ date, type, description, amount, _query_month }]
let adHistory = {};          // 날짜별 광고 데이터 { "2026-02-08": { ad_cost, total_sales, ... } }
let productMapping = {};     // 상품 매핑 { "광고상품명": "로켓SKU명" }
let currentYear = new Date().getFullYear();
let currentMonth = new Date().getMonth() + 1;  // 1-12

// ========================================
// 로컬 스토리지 관리
// ========================================

function loadHistory() {
    try {
        const savedStock = localStorage.getItem(STORAGE_KEY);
        if (savedStock) {
            stockHistory = JSON.parse(savedStock);
        }

        const savedReceiving = localStorage.getItem(RECEIVING_STORAGE_KEY);
        if (savedReceiving) {
            receivingHistory = JSON.parse(savedReceiving);
        }

        const savedDeduction = localStorage.getItem(DEDUCTION_STORAGE_KEY);
        if (savedDeduction) {
            const parsed = JSON.parse(savedDeduction);
            deductionHistory = Array.isArray(parsed) ? parsed : [];
        }

        const savedAd = localStorage.getItem(AD_STORAGE_KEY);
        if (savedAd) {
            adHistory = JSON.parse(savedAd);
        }

        const savedMapping = localStorage.getItem(MAPPING_STORAGE_KEY);
        if (savedMapping) {
            productMapping = JSON.parse(savedMapping);
        }
    } catch (e) {
        console.error('기록 불러오기 실패:', e);
        stockHistory = {};
        receivingHistory = {};
        productMapping = {};
    }
}

function saveHistory() {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(stockHistory));
        localStorage.setItem(RECEIVING_STORAGE_KEY, JSON.stringify(receivingHistory));
        localStorage.setItem(DEDUCTION_STORAGE_KEY, JSON.stringify(deductionHistory));
        localStorage.setItem(AD_STORAGE_KEY, JSON.stringify(adHistory));
        localStorage.setItem(MAPPING_STORAGE_KEY, JSON.stringify(productMapping));
    } catch (e) {
        console.error('기록 저장 실패:', e);
    }
}

/**
 * Supabase(원격 서버)에서 모든 캐시 데이터를 로드하여 localStorage에 병합
 * Vercel 등 원격 환경에서도 데이터를 볼 수 있게 합니다.
 */
async function loadAllCachedData() {
    const endpoints = [
        { url: `${REMOTE_API}/api/cached-stock`, key: 'stock' },
        { url: `${REMOTE_API}/api/cached-receiving`, key: 'receiving' },
        { url: `${REMOTE_API}/api/cached-ad`, key: 'ad' },
        { url: `${REMOTE_API}/api/cached-deduction`, key: 'deduction' }
    ];

    let loaded = 0;
    const results = await Promise.allSettled(endpoints.map(ep => fetch(ep.url).then(r => r.json())));

    results.forEach((result, i) => {
        if (result.status !== 'fulfilled' || !result.value.success) return;
        const data = result.value.data;
        const key = endpoints[i].key;

        if (key === 'stock' && data && typeof data === 'object') {
            // 날짜별 재고 데이터 병합
            Object.keys(data).forEach(date => {
                if (!stockHistory[date]) {
                    stockHistory[date] = data[date];
                }
            });
            loaded++;
        } else if (key === 'receiving' && data && typeof data === 'object') {
            // 날짜별 입고 데이터 병합 (서버 데이터가 더 크면 덮어쓰기)
            Object.keys(data).forEach(date => {
                const serverData = data[date];
                const localData = receivingHistory[date];
                if (!localData || Object.keys(serverData || {}).length > Object.keys(localData || {}).length) {
                    receivingHistory[date] = serverData;
                }
            });
            loaded++;
        } else if (key === 'ad' && data && typeof data === 'object') {
            // 날짜별 광고 데이터 대체
            Object.keys(data).forEach(date => {
                adHistory[date] = data[date];
            });
            loaded++;
        } else if (key === 'deduction' && Array.isArray(data) && data.length > 0) {
            // 정산 데이터 병합 (deductionData + deductionHistory 동기화)
            if (!deductionData || deductionData.length === 0) {
                deductionData = data;
                deductionHistory = data;
                deductionHeaders = data.length > 0 ? Object.keys(data[0]).filter(k => !k.startsWith('_')) : [];
                if (typeof saveDeductionData === 'function') saveDeductionData();
            }
            loaded++;
        }
    });

    if (loaded > 0) {
        saveHistory();
    }
    return loaded;
}

function getTodayString() {
    const today = new Date();
    return today.toISOString().split('T')[0];
}

// ========================================
// 유틸리티 함수
// ========================================

function formatNumber(num) {
    return num.toLocaleString('ko-KR');
}

function formatDateShort(dateStr) {
    const [year, month, day] = dateStr.split('-');
    return `${parseInt(day)}`;  // 일자만 표시
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span>${type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️'}</span>
        <span>${message}</span>
    `;
    elements.toastContainer.appendChild(toast);
    setTimeout(() => {
        toast.style.animation = 'slideInRight 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ========================================
// UI 상태 관리
// ========================================

function hideAllSections() {
    elements.loginSection.classList.add('hidden');
    elements.loadingSection.classList.add('hidden');
    elements.resultSection.classList.add('hidden');
    elements.errorSection.classList.add('hidden');
}

function showLogin() {
    hideAllSections();
    elements.loginSection.classList.remove('hidden');
}

function showLoading(message = '데이터를 불러오는 중...') {
    hideAllSections();
    elements.loadingSection.classList.remove('hidden');

    if (elements.loadingTitle) {
        elements.loadingTitle.textContent = message;
    }

    elements.progressFill.style.animation = 'none';
    elements.progressFill.offsetHeight;
    elements.progressFill.style.animation = 'progress 90s linear';  // 시간 늘림 (입고+재고)
}

function showResult() {
    hideAllSections();
    elements.resultSection.classList.remove('hidden');
}

function showError(message) {
    hideAllSections();
    elements.errorSection.classList.remove('hidden');
    elements.errorMessage.textContent = message;
}

// ========================================
// 월 관리
// ========================================

function getCurrentMonthDates() {
    const result = [];
    const daysInMonth = new Date(currentYear, currentMonth, 0).getDate();

    for (let day = 1; day <= daysInMonth; day++) {
        const dateStr = `${currentYear}-${String(currentMonth).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        result.push(dateStr);
    }

    return result;
}

function updatePeriodLabel() {
    const monthNames = ['1월', '2월', '3월', '4월', '5월', '6월', '7월', '8월', '9월', '10월', '11월', '12월'];
    elements.periodLabel.textContent = `${currentYear}년 ${monthNames[currentMonth - 1]}`;
}

function goToPrevMonth() {
    currentMonth--;
    if (currentMonth < 1) {
        currentMonth = 12;
        currentYear--;
    }
    updatePeriodLabel();
    renderPivotTable();
    updateStats();
}

function goToNextMonth() {
    currentMonth++;
    if (currentMonth > 12) {
        currentMonth = 1;
        currentYear++;
    }
    updatePeriodLabel();
    renderPivotTable();
    updateStats();
}

// ========================================
// 상품 매핑 관리
// ========================================

/**
 * 문자열 유사도 계산 (0~100%)
 * @param {string} str1 - 비교할 문자열 1
 * @param {string} str2 - 비교할 문자열 2
 * @returns {number} - 유사도 (0~100)
 */
function calculateSimilarity(str1, str2) {
    // 전처리: 소문자 변환, 공백/특수문자 제거
    const normalize = (str) => {
        return str.toLowerCase()
            .replace(/[\[\](){}]/g, '') // 괄호 제거
            .replace(/[_-]/g, ' ') // 언더스코어, 하이픈 → 공백
            .replace(/\s+/g, ' ') // 연속 공백 → 단일 공백
            .trim();
    };

    const norm1 = normalize(str1);
    const norm2 = normalize(str2);

    // 완전 일치
    if (norm1 === norm2) return 100;

    // 토큰 기반 매칭
    const tokens1 = norm1.split(' ').filter(t => t.length > 0);
    const tokens2 = norm2.split(' ').filter(t => t.length > 0);

    // 공통 토큰 개수
    let matchCount = 0;
    tokens1.forEach(t1 => {
        if (tokens2.some(t2 => t2.includes(t1) || t1.includes(t2))) {
            matchCount++;
        }
    });

    // 유사도 계산
    const maxTokens = Math.max(tokens1.length, tokens2.length);
    const similarity = maxTokens > 0 ? (matchCount / maxTokens) * 100 : 0;

    return Math.round(similarity);
}

/**
 * 자동 매칭 추천
 * @returns {Object} - { productName: { sku, similarity } }
 */
function suggestAutoMatching() {
    const products = getAllProducts().map(p => p.name);
    const skus = getAllRocketSKUs();
    const suggestions = {};

    products.forEach(product => {
        let bestMatch = null;
        let bestScore = 0;

        skus.forEach(sku => {
            const score = calculateSimilarity(product, sku);
            if (score > bestScore && score >= 60) { // 60% 이상만 추천
                bestMatch = sku;
                bestScore = score;
            }
        });

        if (bestMatch) {
            suggestions[product] = {
                sku: bestMatch,
                similarity: bestScore
            };
        }
    });

    return suggestions;
}

/**
 * 매핑된 입고 수량 가져오기
 * 1순위: 명시적 매핑 (productMapping)
 * 2순위: 자동 키워드 매칭 (매핑 없을 때)
 * @param {string} productName - 광고 상품명
 * @param {string} date - 날짜
 * @returns {number} - 입고 수량 (매핑된 SKU 기준)
 */
function getMappedReceiving(productName, date) {
    try {
        const dayReceiving = receivingHistory[date];
        if (!dayReceiving || typeof dayReceiving !== 'object') return 0;

        // 1) 정확 매칭 (상품명 == SKU명)
        if (dayReceiving[productName] !== undefined) return Number(dayReceiving[productName]) || 0;

        // 2) 수동 매핑 (productMapping)
        const skuName = productMapping[productName];
        if (skuName && dayReceiving[skuName] !== undefined) return Number(dayReceiving[skuName]) || 0;

        return 0;
    } catch(e) {
        return 0;
    }
}

/**
 * 사전 정의된 로켓 SKU 리스트 (입고 상세내역 기준)
 */
const PREDEFINED_SKUS = [
    "파이어 유아 여름 썬캡 챙모자 베어",
    "파이어 유아 여름 썬캡 챙모자 앵두",
    "파이어 유아 여름 썬캡 챙모자 블랙도트",
    "파이어 유아 여름 썬캡 챙모자 컬러도트",
    "주노엘 아동 뽀글이 아노락 상하세트 / 100호 브라운",
    "주노엘 아동 뽀글이 아노락 상하세트 / 110호 브라운",
    "주노엘 아동 뽀글이 아노락 상하세트 / 90호 브라운",
    "주노엘 아동 뽀글이 아노락 상하세트 / 110호 옐로",
    "주노엘 아동 뽀글이 아노락 상하세트 / 100호 옐로",
    "주노엘 아동 뽀글이 아노락 상하세트 / 90호 옐로",
    "주노엘 여아 딸기우유 패딩조끼 핑크, 130호",
    "주노엘 여아 딸기우유 패딩조끼 핑크, 120호",
    "주노엘 여아 딸기우유 패딩조끼 핑크, 110호",
    "주노엘 여아 딸기우유 패딩조끼 핑크, 100호",
    "주노엘 유아 겨울 점퍼 3종세트 / 110",
    "주노엘 유아 겨울 점퍼 3종세트 / 100",
    "주노엘 유아 겨울 점퍼 3종세트 / 120",
    "주노엘 유아 겨울 점퍼 3종세트 / 90",
    "주노엘 여아 데님 3종세트 / 100",
    "주노엘 여아 데님 3종세트 / 130",
    "주노엘 여아 데님 3종세트 / 120",
    "주노엘 여아 데님 3종세트 / 110",
    "[오늘도착] 주노엘 여아 기모 리본 상하복 세트 / 100",
    "[오늘도착] 주노엘 여아 기모 리본 상하복 세트 / 110",
    "[오늘도착] 주노엘 여아 기모 리본 상하복 세트 / 120",
    "[오늘도착] 주노엘 여아 기모 리본 상하복 세트 / 130",
    "당일출고 접이식피아노 전자 디지털 피아노 / 화이트 88건반",
    "당일출고 접이식피아노 전자 디지털 피아노 / 블랙 88건반",
    "KC인증 당일출고 접이식 전자피아노 입문용 교습용 88건반 61건반 / 블랙 61건반",
    "KC인증 당일출고 접이식 전자피아노 입문용 교습용 88건반 61건반 / 화이트 61건반",
    "노엘 KC인증 당일출고 접이식피아노 휴대용 입문용 교습용 / 블랙 88건반",
    "노엘 KC인증 당일출고 접이식피아노 휴대용 입문용 교습용 / 화이트 88건반",
    "KC인증 당일출고 접이식피아노 휴대용 입문용 교습용 / 화이트 61건반",
    "KC인증 당일출고 접이식피아노 휴대용 입문용 교습용 / 블랙 61건반",
    "오랑우탄 키링 인형 고릴라 키홀더 / 브라운 1개",
    "슬픈 눈을 가진 포우 애착 인형 봉제 22cm / 22cm",
    "주노엘 카피바라 귀여운 동물 애착인형, 22cm 1개",
    "KC인증 RC카 수륙양용 무선조종, 1개 혼합색상",
    "주노엘 대형물탱크 자동 연발 물총 워터건, 핑크, 1개",
    "주노엘 대형물탱크 자동 연발 물총 워터건, 블루, 1개",
    "주노엘 KC인증 LED 라이트 나오는 USB충전식 배터리 물총, 핑크, 1개",
    "주노엘 KC인증 LED 라이트 나오는 USB충전식 배터리 물총, 블루, 1개",
    "람보르기니 우라칸 STO 1:24 장난감 자동차 / 단일상품",
    "주노엘 핑크 RC카 오프로드 대형 30CM 무선조종, 1개",
    "주노엘 RC카 무선조종 미니보트 31cm, 혼합색상, 1개",
    "주노엘 RC카 무선조종 스쿨버스 1:30, 혼합색상, 1개",
    "주노엘 RC카 무선조종 구급차 1:30, 혼합색상, 1개",
    "주노엘 버니쿨 무드등 선풍기 탁상용 선물용, 연퍼플 D-22",
    "주노엘 버니쿨 선풍기 무드등 올인원, 개나리 D-22",
    "주노엘 버니쿨 선풍기 무드등 올인원, 인디핑크 D-22",
    "주노엘 오랑우탄 인형 고릴라 고숭이 오숭이 동물인형 19cm, 1개",
    "주노엘 딸기우유빛 핑크 오프로드 RC카, 1개",
    "주노엘 범퍼카 리모콘 배틀카 스포츠게임 배틀라이더, 범퍼카(블루+핑크) 2대, 1개",
    "주노엘 중장비 장난감 RC지게차 포크리프트 무선조종, 포크리프트 지게차 1개 혼합색상",
    "주노엘 카피바라 물총 세트 단일색상 2개",
    "주노엘 결혼하는 카피바라 커플 키링 신랑 혼합색상 11cm",
    "주노엘 결혼하는 카피바라 커플 키링 신부 혼합색상 11cm",
    "주노엘 불꽃 자동 펌핑 LED 워터건, 레드",
    "주노엘 불꽃 자동 펌핑 LED 워터건, 블루",
    "주노엘 불꽃 자동 펌핑 LED 워터건, 그레이",
    "주노엘 핑크 포크레인 RC카 핑크 1세트, 260x95x160mm",
    "주노엘 중장비 장난감 굴삭기 불도저 롤러 3종 RC카, 1세트, 혼합색상",
    "주노엘 토끼 파스텔 키링 열쇠고리 시리즈, 1개, 간호사 토끼",
    "주노엘 토끼 파스텔 키링 열쇠고리 시리즈, 1개, 생일파티 토끼",
    "주노엘 토끼 파스텔 키링 열쇠고리 시리즈, 1개, 멜빵바지 토끼",
    "주노엘 토끼 파스텔 키링 열쇠고리 시리즈, 1개, 피에로 토끼",
    "주노엘 토끼 파스텔 키링 열쇠고리 시리즈, 1개, 팬더 토끼",
    "주노엘 날개파닥 꿀벌 카피바라 키링 열쇠고리 혼합색상 1개 155mm",
    "주노엘 카피바라 친구들 키링 열쇠고리 인형, 1개, 라부 가방 (브라운) 카피바라",
    "주노엘 카피바라 친구들 키링 열쇠고리 인형, 1개, 크리스마스 카피바라",
    "주노엘 카피바라 친구들 키링 열쇠고리 인형, 1개, 바비걸 카피바라(애플)",
    "주노엘 카피바라 친구들 키링 열쇠고리 인형, 1개, 라부 가방 (퍼플) 카피바라",
    "주노엘 카피바라 친구들 키링 열쇠고리 인형, 1개, 붕어빵 먹는 카피바라",
    "주노엘 카피바라 친구들 키링 열쇠고리 인형, 1개, 탕후루 먹는 카피바라",
    "주노엘 카피바라 친구들 키링 열쇠고리 인형, 1개, 라부 가방 (연핑크) 카피바라",
    "주노엘 카피바라 친구들 키링 열쇠고리 인형, 1개, 바비걸 카피바라(리본)",
    "주노엘 라부부 투명 수납 보호 케이스 앉음형 8 x 8.6 x 15.5 cm",
    "주노엘 라부부 투명 수납 보호 케이스 스탠딩형 10.5 x 8.6 x 17 cm",
    "주노엘 카피바라 친구들 키링 열쇠고리 인형, 1개, 라부 가방 (화이트) 카피바라",
    "주노엘 카피바라 친구들 키링 열쇠고리 인형, 1개, 라부 가방 (노랑) 카피바라",
    "주노엘 카피바라 친구들 키링 열쇠고리 인형, 1개, 라부 가방 (진핑크) 카피바라",
    "주노엘 중장비 장난감 무선조종 RC카  굴삭기 혼합색상 1개 24 x 11 x 9 cm",
    "주노엘 중장비 장난감 무선조종 RC카 불도저 1개 23 x 10 x 10 cm 혼합색상",
    "주노엘 중장비 장난감 무선조종 RC카 롤러 1개 혼합색상 20 x 10  x 10 cm",
    "주노엘 라부부 옷 (인형미포함), 스마일멜빵바지",
    "주노엘 라부부 옷 (인형미포함), 꿀벌 1세트",
    "주노엘 라부부 옷 (인형미포함), 트위드 화이트숄 모자세트 1세트",
    "주노엘 라부부 옷 (인형미포함), 크리미멜빵바지세트 1세트",
    "주노엘 라부부 옷 (인형미포함), 할로윈 펌킨세트 1세트",
    "주노엘 라부부 옷 (인형미포함), 할로윈 블랙 펌킨세트 1세트",
    "주노엘 라부부 옷 (인형미포함), 할로윈 붉은악마 1세트",
    "주노엘 라부부 옷 (인형미포함), 트위드 샤원피스 3종세트 1세트",
    "주노엘 라부부 옷 (인형미포함), 핑크솜사탕세트 1세트",
    "주노엘 라부부 옷 (인형미포함), 브라운멜빵바지세트 1세트",
    "주노엘 라부부 옷 (인형미포함), 핑크멜빵바지세트 1세트",
    "주노엘 라부부 옷 (인형미포함), 트위드 원피스 4종세트 1세트",
    "주노엘 라부부 옷 (인형미포함), 크리스마스 망또 1개",
    "누디아 니플 패치 리필 원형 / 원형 4장",
    "누디아 니플 패치 리필 원형 / 원형 10장",
    "주노엘 폭신오리 포근포근 노란 부리 오리 인형, 1개, 300mm 단일색상",
    "주노엘 라부부 옷 (인형미포함), 화이트멜빵바지세트 1세트",
    "주노엘 라부부 옷 (인형미포함), 마리오",
    "주노엘 라부부 옷 (인형미포함), 카푸치노세트",
    "주노엘 라부부 옷 (인형미포함), 그린줄무늬세트",
    "주노엘 라부부 옷 (인형미포함), 할로윈 악마날개 펌킨세트",
    "주노엘 라부부 옷 (인형미포함), 블랙진뜨게 4종세트",
    "주노엘 라부부 옷 (인형미포함), 크리스마스 산타복",
    "주노엘 라부부 옷 (인형미포함), 크리스마스 루돌프",
    "주노엘 라부부 옷 (인형미포함), 트위드 블랙숄 모자세트",
    "주노엘 라부부 옷 (인형미포함), 하트데님4종세트",
    "주노엘 라부부 옷 (인형미포함), 스카이멜빵바지세트",
    "주노엘 라부부 옷 (인형미포함), 알바생"
];

/**
 * 모든 로켓 SKU명 수집 (입고 이력 + 사전 정의 SKU)
 */
function getAllRocketSKUs() {
    const skuSet = new Set();

    // 입고 이력에서 수집
    Object.values(receivingHistory).forEach(dayData => {
        Object.keys(dayData).forEach(sku => skuSet.add(sku));
    });

    // 사전 정의된 SKU 추가
    PREDEFINED_SKUS.forEach(sku => skuSet.add(sku));

    return Array.from(skuSet).sort();
}

// ========================================
// 피벗 테이블 렌더링
// ========================================

/**
 * 모든 상품명 수집 (광고 상품 우선 정렬)
 */
function getAllProducts() {
    const productMap = new Map();
    const dates = getCurrentMonthDates();

    Object.values(stockHistory).forEach(dayData => {
        dayData.forEach(item => {
            const existing = productMap.get(item.product_name);
            if (!existing || item.ad_status === '광고중') {
                productMap.set(item.product_name, item.ad_status || '광고안함');
            }
        });
    });

    // 현재 월 판매량 계산 (직접 입고 조회)
    const salesMap = {};
    productMap.forEach((_, productName) => {
        let prevStock = null;
        let totalSales = 0;
        dates.forEach(date => {
            const dayData = stockHistory[date];
            if (!dayData) return;
            const item = dayData.find(d => d.product_name === productName);
            if (!item) return;
            if (prevStock !== null) {
                let receiving = 0;
                try {
                    const _dr = receivingHistory[date];
                    if (_dr && typeof _dr === 'object') {
                        if (_dr[productName] !== undefined) {
                            receiving = Number(_dr[productName]) || 0;
                        }
                        if (receiving === 0) {
                            const mappedSku = productMapping[productName];
                            if (mappedSku && _dr[mappedSku] !== undefined) {
                                receiving = Number(_dr[mappedSku]) || 0;
                            }
                        }
                    }
                } catch(e) {}
                const sales = prevStock + receiving - item.stock;
                if (sales > 0) totalSales += sales;
            }
            prevStock = item.stock;
        });
        salesMap[productName] = totalSales;
    });

    // 정렬: 판매량 있는 상품 상단 → 광고중 → 이름순
    const products = Array.from(productMap.entries());
    products.sort((a, b) => {
        const aSales = salesMap[a[0]] || 0;
        const bSales = salesMap[b[0]] || 0;
        if (aSales > 0 && bSales === 0) return -1;
        if (aSales === 0 && bSales > 0) return 1;
        if (aSales !== bSales) return bSales - aSales;
        const aIsAd = a[1] === '광고중';
        const bIsAd = b[1] === '광고중';
        if (aIsAd && !bIsAd) return -1;
        if (!aIsAd && bIsAd) return 1;
        return a[0].localeCompare(b[0]);
    });

    return products.map(p => ({ name: p[0], adStatus: p[1] }));
}

/**
 * 피벗 테이블 렌더링 (입고 | 재고 | 판매)
 */
function renderPivotTable() {
    const dates = getCurrentMonthDates();
    const products = getAllProducts();
    const today = getTodayString();


    if (products.length === 0) {
        elements.pivotTableHead.innerHTML = '';
        elements.pivotTableBody.innerHTML = '<tr><td colspan="100" style="text-align:center;padding:40px;color:var(--text-muted);">데이터가 없습니다. "새로 조회" 버튼을 클릭하여 재고를 조회하세요.</td></tr>';
        return;
    }

    // 헤더 생성 (날짜 행 + 입고/재고/판매 행)
    let headerRow1 = '<tr><th class="product-header">상품명</th>';
    let headerRow2 = '<tr><th class="product-header-sub"></th>';

    dates.forEach(date => {
        const isToday = date === today;
        const hasStockData = stockHistory[date] !== undefined;
        const hasReceivingData = receivingHistory[date] !== undefined;
        const hasData = hasStockData || hasReceivingData;
        const todayClass = isToday ? ' today' : '';
        const opacity = hasData ? '' : ' style="opacity: 0.3;"';

        headerRow1 += `<th colspan="3" class="date-header${todayClass}"${opacity}>${formatDateShort(date)}</th>`;
        headerRow2 += `<th class="sub-header receiving-label">입고</th><th class="sub-header stock-label">재고</th><th class="sub-header sales-label">판매</th>`;
    });

    headerRow1 += '</tr>';
    headerRow2 += '</tr>';
    elements.pivotTableHead.innerHTML = headerRow1 + headerRow2;

    // 상품별 데이터 렌더링
    let bodyHtml = '';

    products.forEach(product => {
        const productName = product.name;
        const adStatus = product.adStatus;
        const hasMappedSKU = productMapping[productName] ? true : false;

        const adBadge = adStatus === '광고중' ? '<span class="ad-badge">광고</span>' : '';
        const mappingStatus = hasMappedSKU ? '' : '<span class="mapping-warning" title="입고 SKU 매핑 필요">⚠️</span>';
        bodyHtml += `<tr><td class="product-name-cell">${adBadge}${mappingStatus}${escapeHtml(productName)}</td>`;

        let prevStock = null;

        dates.forEach(date => {
            const dayStockData = stockHistory[date];

            // 입고 조회: 정확매칭 → 수동매핑 → 부분매칭(자동)
            let receiving = 0;
            try {
                const _dr = receivingHistory[date];
                if (_dr && typeof _dr === 'object') {
                    // 1) 정확 매칭 (상품명 == SKU명)
                    if (_dr[productName] !== undefined) {
                        receiving = Number(_dr[productName]) || 0;
                    }
                    // 2) 수동 매핑 (productMapping)
                    if (receiving === 0) {
                        const mappedSku = productMapping[productName];
                        if (mappedSku && _dr[mappedSku] !== undefined) {
                            receiving = Number(_dr[mappedSku]) || 0;
                        }
                    }
                }
            } catch(e) {}

            // 입고 표시 HTML
            const receivingHtml = receiving > 0
                ? `<span class="receiving-cell positive">+${receiving}</span>`
                : '<span class="empty-cell">-</span>';

            if (dayStockData) {
                const item = dayStockData.find(d => d.product_name === productName);

                if (item) {
                    const stock = item.stock;

                    // 판매량 계산: 전날재고 + 오늘입고 - 오늘재고
                    let salesHtml = '-';
                    if (prevStock !== null) {
                        const sales = prevStock + receiving - stock;
                        if (sales > 0) {
                            salesHtml = `<span class="sales-cell positive">${sales}</span>`;
                        } else if (sales < 0) {
                            salesHtml = `<span class="sales-cell negative">${sales}</span>`;
                        } else {
                            salesHtml = '<span class="empty-cell">0</span>';
                        }
                    }

                    bodyHtml += `<td>${receivingHtml}</td>`;
                    bodyHtml += `<td class="stock-cell">${stock}</td>`;
                    bodyHtml += `<td>${salesHtml}</td>`;

                    prevStock = stock;
                } else {
                    // 재고 없지만 입고 있으면 표시
                    bodyHtml += `<td>${receivingHtml}</td><td class="empty-cell">-</td><td class="empty-cell">-</td>`;
                }
            } else {
                // 재고 데이터 없는 날짜도 입고는 표시
                bodyHtml += `<td>${receivingHtml}</td><td class="empty-cell">-</td><td class="empty-cell">-</td>`;
            }
        });

        bodyHtml += '</tr>';
    });

    elements.pivotTableBody.innerHTML = bodyHtml;
}

/**
 * 통계 업데이트 (현재 월 기준)
 */
function updateStats() {
    const products = getAllProducts();
    const monthDates = getCurrentMonthDates();
    const recordedDates = monthDates.filter(d => stockHistory[d]);

    if (elements.totalItems) {
        elements.totalItems.textContent = formatNumber(products.length);
    }

    if (elements.recordDays) {
        elements.recordDays.textContent = formatNumber(recordedDates.length);
    }

    // 이번 달 총 판매량 (새로운 계산: 전날재고 + 입고 - 오늘재고)
    if (elements.totalSalesMonth) {
        let totalSales = 0;

        products.forEach(product => {
            let prevStock = null;

            recordedDates.forEach(date => {
                const dayData = stockHistory[date];
                if (dayData) {
                    const item = dayData.find(d => d.product_name === product.name);
                    if (item) {
                        if (prevStock !== null) {
                            const receiving = getMappedReceiving(product.name, date);
                            const sales = prevStock + receiving - item.stock;
                            if (sales > 0) {
                                totalSales += sales;
                            }
                        }
                        prevStock = item.stock;
                    }
                }
            });
        });

        if (totalSales > 0) {
            elements.totalSalesMonth.innerHTML = `<span style="color: var(--success);">${formatNumber(totalSales)}개</span>`;
        } else {
            elements.totalSalesMonth.textContent = '-';
        }
    }
}

// ========================================
// API 호출
// ========================================

async function fetchStockAndReceiving(userId, userPw) {
    showLoading('재고 데이터를 불러오는 중...');

    const loadingMessages = [
        '쿠팡에 로그인하고 있습니다...',
        '광고하지 않는 상품 재고 수집 중...',
        '광고 중인 상품 재고 수집 중...',
        '데이터를 분석하고 있습니다...'
    ];

    let messageIndex = 0;
    const messageInterval = setInterval(() => {
        messageIndex = (messageIndex + 1) % loadingMessages.length;
        elements.loadingStatus.textContent = loadingMessages[messageIndex];
    }, 5000);

    try {
        elements.loadingStatus.textContent = '📦 재고 데이터 조회 중...';
        const stockResponse = await fetch(`${API_BASE_URL}/api/fetch-stock`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: userId,
                user_pw: userPw,
                include_ad_report: false
            })
        });

        if (!stockResponse.ok) {
            throw new Error(`재고 조회 실패: ${stockResponse.status}`);
        }

        const stockResult = await stockResponse.json();

        if (!stockResult.success) {
            throw new Error(stockResult.error || '재고 데이터 조회 실패');
        }

        // 재고 데이터 저장
        const today = getTodayString();
        stockHistory[today] = stockResult.data;
        const stockCount = stockResult.count;

        clearInterval(messageInterval);
        saveHistory();

        // 오늘 날짜의 월로 설정
        const todayDate = new Date();
        currentYear = todayDate.getFullYear();
        currentMonth = todayDate.getMonth() + 1;

        updatePeriodLabel();
        renderPivotTable();
        updateStats();
        showResult();

        showToast(`✅ 재고 수집 완료! ${stockCount}개 상품`, 'success');

    } catch (error) {
        clearInterval(messageInterval);
        console.error('API Error:', error);
        showError(error.message || '서버 연결에 실패했습니다.');
    }
}

/**
 * 입고 데이터만 단독 조회
 */
async function fetchReceivingDataOnly(userId, userPw) {
    showLoading('입고 데이터를 불러오는 중...');
    elements.loadingStatus.textContent = '📥 입고 데이터 조회 중...';

    const loadingMessages = [
        '쿠팡에 로그인하고 있습니다...',
        '물류 메뉴로 이동 중...',
        '입고상세내역을 확인하고 있습니다...',
        '데이터를 분석하고 있습니다...'
    ];

    let messageIndex = 0;
    const messageInterval = setInterval(() => {
        messageIndex = (messageIndex + 1) % loadingMessages.length;
        elements.loadingStatus.textContent = loadingMessages[messageIndex];
    }, 5000);

    try {
        const receivingResponse = await fetch(`${API_BASE_URL}/api/fetch-receiving`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId, user_pw: userPw })
        });

        if (!receivingResponse.ok) {
            const errorText = await receivingResponse.text();
            throw new Error(`입고 조회 실패: ${receivingResponse.status} ${errorText}`);
        }

        const receivingResult = await receivingResponse.json();

        if (!receivingResult.success) {
            throw new Error(receivingResult.error || '입고 데이터 조회 실패');
        }

        // 입고 데이터 저장 (날짜별 그룹핑)
        let receivingCount = 0;

        if (receivingResult.data_by_date && typeof receivingResult.data_by_date === 'object') {
            // 서버에서 날짜별로 그룹핑된 데이터 사용
            Object.entries(receivingResult.data_by_date).forEach(([date, skuData]) => {
                receivingHistory[date] = skuData;
            });
            receivingCount = Object.keys(receivingResult.data_by_date).reduce((sum, d) => sum + Object.keys(receivingResult.data_by_date[d]).length, 0);
        } else if (Array.isArray(receivingResult.data)) {
            // 폴백: date 필드가 있으면 날짜별 그룹핑
            const dateGrouped = {};
            receivingResult.data.forEach(item => {
                if (item.sku_name) {
                    const d = item.date || getTodayString();
                    if (!dateGrouped[d]) dateGrouped[d] = {};
                    dateGrouped[d][item.sku_name] = (dateGrouped[d][item.sku_name] || 0) + item.quantity;
                }
            });
            Object.entries(dateGrouped).forEach(([date, skuData]) => {
                receivingHistory[date] = skuData;
            });
            receivingCount = receivingResult.data.length;
        }

        saveHistory();

        // UI 업데이트
        clearInterval(messageInterval);

        // 오늘 날짜의 월로 설정
        const todayDate = new Date();
        currentYear = todayDate.getFullYear();
        currentMonth = todayDate.getMonth() + 1;

        updatePeriodLabel();
        renderPivotTable();
        updateStats(); // 통계 업데이트 포함

        // 결과 섹션 표시
        elements.loadingSection.classList.add('hidden');
        elements.resultSection.classList.remove('hidden');

        const dateCount = receivingResult.data_by_date ? Object.keys(receivingResult.data_by_date).length : 1;
        showToast(`✅ 입고 조회 완료! ${dateCount}일 ${receivingCount}건 수집됨`, 'success');

        // 매핑 필요 여부 확인
        checkMappingNeeded();

    } catch (error) {
        clearInterval(messageInterval);
        console.error('API Error:', error);
        showError(error.message || '서버 연결에 실패했습니다.');
    }
}

// 입고 수집 버튼 이벤트 리스너
document.addEventListener('click', async (e) => {
    if (e.target.id === 'fetchReceivingBtn' || e.target.closest('#fetchReceivingBtn')) {
        console.log('📥 입고 수집 버튼 클릭됨');
        const { userId, userPw } = getCredentials();

        if (!userId || !userPw) {
            console.log('⚠️ 로그인 정보 없음 - userId:', !!userId, 'userPw:', !!userPw);
            showToast('먼저 재고 탭에서 로그인해주세요.', 'error');
            return;
        }

        console.log('📥 입고 수집 시작...');
        await fetchReceivingDataOnly(userId, userPw);
    }
});


async function fetchAllData(userId, userPw) {
    showLoading('전체 데이터를 불러오는 중...');

    const loadingMessages = [
        '쿠팡에 로그인하고 있습니다...',
        '재고 데이터 수집 중...',
        '광고비 데이터 수집 중...',
        '입고 + 정산 데이터 수집 중...',
        '데이터를 분석하고 있습니다...'
    ];

    let messageIndex = 0;
    const messageInterval = setInterval(() => {
        messageIndex = (messageIndex + 1) % loadingMessages.length;
        elements.loadingStatus.textContent = loadingMessages[messageIndex];
    }, 8000);

    let stockCount = 0;
    let deductionCount = 0;
    let adOk = false;
    let receivingOk = false;
    const errors = [];

    try {
        // [1/3] 재고 데이터 조회
        elements.loadingStatus.textContent = '📦 [1/3] 재고 데이터 조회 중...';
        try {
            const stockResponse = await fetch(`${API_BASE_URL}/api/fetch-stock`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, user_pw: userPw })
            });
            const stockResult = await stockResponse.json();
            if (stockResult.success) {
                const today = getTodayString();
                stockHistory[today] = stockResult.data;
                stockCount = stockResult.count;
            } else {
                errors.push('재고');
            }
        } catch (e) { errors.push('재고'); console.error('재고 수집 오류:', e); }

        // [2/3] 광고비 데이터 조회 (백그라운드 수집)
        elements.loadingStatus.textContent = '📊 [2/3] 광고비 수집 요청 중...';
        try {
            const adResponse = await fetch(`${API_BASE_URL}/api/fetch-ad-report`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, user_pw: userPw, days_back: 7 })
            });
            const adResult = await adResponse.json();
            if (adResult.success) {
                if (adResult.background) {
                    // 백그라운드 수집 시작됨 → 나중에 캐시에서 로드
                    console.log('📊 광고비 백그라운드 수집 시작됨');
                    adOk = true;
                } else if (adResult.data_by_date) {
                    for (const [dateStr, dayData] of Object.entries(adResult.data_by_date)) {
                        const existing = adHistory[dateStr];
                        if (existing && existing.products && existing.products.length > 0 && (!dayData.products || dayData.products.length === 0)) {
                            dayData.products = existing.products;
                        }
                        adHistory[dateStr] = dayData;
                    }
                    adOk = true;
                }
            } else {
                errors.push('광고');
            }
        } catch (e) { errors.push('광고'); console.error('광고 수집 오류:', e); }

        // [3/3] 입고 + 정산 통합 수집 (supplier.coupang.com 1회 로그인)
        elements.loadingStatus.textContent = '📥 [3/3] 입고 + 정산 데이터 수집 중... (1회 로그인)';
        let receivingCount = 0;
        try {
            const supplierResponse = await fetch(`${API_BASE_URL}/api/fetch-supplier-all`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, user_pw: userPw, days_back: 7 })
            });
            const supplierResult = await supplierResponse.json();

            // 입고 결과 처리 (정산과 분리)
            try {
                const rec = supplierResult.receiving;
                if (rec && rec.success) {
                    if (rec.data_by_date && typeof rec.data_by_date === 'object') {
                        const dates = Object.keys(rec.data_by_date);
                        for (const [dateStr, skuData] of Object.entries(rec.data_by_date)) {
                            receivingHistory[dateStr] = skuData;
                        }
                        receivingCount = dates.length;
                    }
                    receivingOk = true;
                } else {
                    errors.push('입고');
                }
            } catch (recErr) {
                errors.push('입고');
                console.error('입고 처리 오류:', recErr);
            }

            // 정산 결과 처리 (입고와 분리)
            try {
                const ded = supplierResult.deduction;
                if (ded && ded.success) {
                    if (ded.data && ded.data.length > 0) {
                        // 월별 병합: 새 데이터의 월만 교체, 나머지 월 보존
                        const newMonths = new Set(ded.data.map(r => r._query_month).filter(Boolean));
                        const kept = (Array.isArray(deductionHistory) ? deductionHistory : []).filter(r => !newMonths.has(r._query_month));
                        deductionHistory = [...kept, ...ded.data];
                        deductionCount = deductionHistory.length;
                        // deductionData도 동기화 (정산내역/손익현황 탭에서 사용)
                        deductionData = deductionHistory;
                        deductionHeaders = deductionHistory.length > 0 ? Object.keys(deductionHistory[0]).filter(k => !k.startsWith('_')) : [];
                        saveDeductionData();
                    }
                } else {
                    errors.push('정산');
                }
            } catch (dedErr) {
                errors.push('정산');
                console.error('정산 처리 오류:', dedErr);
            }
        } catch (e) {
            console.error('공급자 통합 수집 오류:', e);
            // 네트워크 중단(ERR_NETWORK_IO_SUSPENDED) 시 캐시에서 복구 시도
            // 백엔드는 수집 완료 후 Supabase에 이미 저장했을 가능성 높음
            console.log('네트워크 오류 → 서버 캐시에서 복구 시도...');
            elements.loadingStatus.textContent = '⏳ 연결 끊김 - 서버 데이터 확인 중...';
            await new Promise(r => setTimeout(r, 5000));

            let recovered = false;
            try {
                // 입고 캐시 로드
                const cachedRecRes = await fetch(`${API_BASE_URL}/api/cached-receiving`);
                const cachedRec = await cachedRecRes.json();
                if (cachedRec.success && cachedRec.data && Object.keys(cachedRec.data).length > 0) {
                    const beforeCount = Object.keys(receivingHistory).length;
                    Object.entries(cachedRec.data).forEach(([d, skus]) => {
                        receivingHistory[d] = skus;
                    });
                    const afterCount = Object.keys(receivingHistory).length;
                    if (afterCount > beforeCount) {
                        receivingOk = true;
                        receivingCount = afterCount - beforeCount;
                        recovered = true;
                        console.log(`캐시에서 입고 복구: ${receivingCount}일`);
                    }
                }

                // 정산 캐시 로드
                const cachedDedRes = await fetch(`${API_BASE_URL}/api/cached-deduction`);
                const cachedDed = await cachedDedRes.json();
                if (cachedDed.success && cachedDed.data && Array.isArray(cachedDed.data) && cachedDed.data.length > 0) {
                    deductionHistory = cachedDed.data;
                    deductionCount = cachedDed.count || cachedDed.data.length;
                    // deductionData도 동기화
                    deductionData = deductionHistory;
                    deductionHeaders = deductionHistory.length > 0 ? Object.keys(deductionHistory[0]).filter(k => !k.startsWith('_')) : [];
                    saveDeductionData();
                    recovered = true;
                    console.log(`캐시에서 정산 복구: ${deductionCount}건`);
                }
            } catch (cacheErr) {
                console.error('캐시 복구 실패:', cacheErr);
            }

            if (!recovered) {
                errors.push('입고+정산');
            }
        }

        clearInterval(messageInterval);
        saveHistory();

        // 항상 Supabase에서 입고 데이터 보충 확인 (캐시 병합)
        try {
            const verifyRes = await fetch(`${API_BASE_URL}/api/cached-receiving`);
            const verifyData = await verifyRes.json();
            if (verifyData.success && verifyData.data) {
                let addedCount = 0;
                for (const [d, skus] of Object.entries(verifyData.data)) {
                    if (!receivingHistory[d]) {
                        receivingHistory[d] = skus;
                        addedCount++;
                    }
                }
                if (addedCount > 0) {
                    console.log(`Supabase에서 ${addedCount}일 보충`);
                    receivingCount += addedCount;
                    saveHistory();
                }
            }
        } catch (verifyErr) {
            // Supabase 검증 스킵
        }

        // 오늘 날짜의 월로 설정
        const todayDate = new Date();
        currentYear = todayDate.getFullYear();
        currentMonth = todayDate.getMonth() + 1;

        updatePeriodLabel();
        renderPivotTable();
        updateStats();
        renderDeductionTable();
        if (typeof renderAdTab === 'function') renderAdTab();
        showResult();

        // 결과 메시지 (입고 건수 포함)
        const recMsg = receivingCount > 0 ? `, 입고 ${receivingCount}일치` : '';
        if (errors.length === 0) {
            showToast(`✅ 전체 수집 완료! 재고 ${stockCount}개${recMsg}, 정산 ${deductionCount}건`, 'success');
        } else {
            showToast(`⚠️ 수집 완료 (${errors.join(', ')} 실패) | 재고 ${stockCount}개${recMsg}, 정산 ${deductionCount}건`, 'warning');
        }

        checkMappingNeeded();

    } catch (error) {
        clearInterval(messageInterval);
        console.error('API Error:', error);
        showError(error.message || '서버 연결에 실패했습니다.');
    }
}

/**
 * 매핑이 필요한 상품 확인 및 자동 매칭 모달 표시
 */
function checkMappingNeeded() {
    const products = getAllProducts();
    const unmapped = products.filter(p => !productMapping[p.name]);

    if (unmapped.length > 0 && Object.keys(receivingHistory).length > 0) {
        // 자동 매칭 모달 표시 (유사도 기반 추천)
        setTimeout(() => {
            showMappingModal(true);
        }, 500); // UI 렌더링 후 모달 표시
    }
}

// ========================================
// 상품 매핑 모달
// ========================================

function showMappingModal(autoSuggest = false) {
    const products = getAllProducts();
    const rocketSKUs = getAllRocketSKUs();

    if (rocketSKUs.length === 0) {
        showToast('입고 데이터가 없습니다. 먼저 데이터를 조회하세요.', 'error');
        return;
    }

    // 자동 매칭 추천
    const suggestions = autoSuggest ? suggestAutoMatching() : {};

    // 모달 생성
    const modal = document.createElement('div');
    modal.className = 'mapping-modal';
    modal.innerHTML = `
        <div class="mapping-modal-content">
            <div class="mapping-modal-header">
                <h3>🔗 상품 매핑 설정 ${autoSuggest ? '(자동 추천)' : ''}</h3>
                <button class="close-btn" onclick="this.closest('.mapping-modal').remove()">✕</button>
            </div>
            <p class="mapping-desc">광고 상품명과 로켓 SKU명을 매핑하세요. ${autoSuggest ? '<strong>✨ 유사도 기반 자동 추천이 적용되었습니다.</strong>' : '판매량 계산에 사용됩니다.'}</p>
            ${autoSuggest ? '<div style="padding: 0 var(--spacing-lg); margin-bottom: var(--spacing-sm);"><button class="btn btn-sm btn-success" id="acceptAllBtn">✅ 모두 승인</button></div>' : ''}
            <div class="mapping-list">
                ${products.map(p => {
        const suggested = suggestions[p.name];
        const currentMapping = productMapping[p.name];
        const defaultSku = currentMapping || (suggested ? suggested.sku : '');

        return `
                        <div class="mapping-row">
                            <span class="ad-product-name" title="${escapeHtml(p.name)}">${escapeHtml(p.name)}</span>
                            <span class="mapping-arrow">→</span>
                            <select class="sku-select" data-product="${escapeHtml(p.name)}">
                                <option value="">선택 안 함</option>
                                ${rocketSKUs.map(sku => `
                                    <option value="${escapeHtml(sku)}" ${defaultSku === sku ? 'selected' : ''}>
                                        ${escapeHtml(sku)}
                                    </option>
                                `).join('')}
                            </select>
                            ${suggested && !currentMapping ? `<span class="similarity-badge" title="유사도 ${suggested.similarity}%">✨ ${suggested.similarity}%</span>` : ''}
                        </div>
                    `;
    }).join('')}
            </div>
            <div class="mapping-modal-footer">
                <button class="btn btn-secondary" onclick="this.closest('.mapping-modal').remove()">취소</button>
                <button class="btn btn-primary" id="saveMappingBtn">저장</button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    // 모두 승인 버튼
    const acceptAllBtn = document.getElementById('acceptAllBtn');
    if (acceptAllBtn) {
        acceptAllBtn.addEventListener('click', () => {
            Object.keys(suggestions).forEach(productName => {
                productMapping[productName] = suggestions[productName].sku;
            });
            saveHistory();
            modal.remove();
            renderPivotTable();
            updateStats();
            showToast(`${Object.keys(suggestions).length}개 매핑 자동 적용 완료!`, 'success');
        });
    }

    // 저장 버튼 이벤트
    document.getElementById('saveMappingBtn').addEventListener('click', () => {
        const selects = modal.querySelectorAll('.sku-select');
        selects.forEach(select => {
            const productName = select.dataset.product;
            const skuName = select.value;
            if (skuName) {
                productMapping[productName] = skuName;
            } else {
                delete productMapping[productName];
            }
        });
        saveHistory();
        modal.remove();
        renderPivotTable();
        updateStats();
        showToast('매핑 저장 완료!', 'success');
    });
}

// ========================================
// 엑셀 다운로드
// ========================================

function downloadExcel() {
    const dates = getCurrentMonthDates().filter(d => stockHistory[d] || receivingHistory[d]);
    const products = getAllProducts();

    if (dates.length === 0) {
        showToast('다운로드할 데이터가 없습니다.', 'error');
        return;
    }

    // CSV 헤더 (입고/재고/판매 3컬럼)
    let headers = ['광고', '상품명'];
    dates.forEach(date => {
        headers.push(`${formatDateShort(date)}일_입고`);
        headers.push(`${formatDateShort(date)}일_재고`);
        headers.push(`${formatDateShort(date)}일_판매`);
    });

    const rows = products.map(product => {
        const row = [product.adStatus === '광고중' ? 'O' : '', product.name];
        let prevStock = null;

        dates.forEach(date => {
            const receiving = getMappedReceiving(product.name, date);
            const dayData = stockHistory[date];

            if (dayData) {
                const item = dayData.find(d => d.product_name === product.name);
                if (item) {
                    row.push(receiving || '-');
                    row.push(item.stock);

                    if (prevStock !== null) {
                        const sales = prevStock + receiving - item.stock;
                        row.push(sales);
                    } else {
                        row.push('-');
                    }
                    prevStock = item.stock;
                } else {
                    row.push('-', '-', '-');
                }
            } else {
                row.push('-', '-', '-');
            }
        });

        return row;
    });

    let csvContent = '\uFEFF';
    csvContent += headers.join(',') + '\n';
    csvContent += rows.map(row => row.map(cell => `"${cell}"`).join(',')).join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `재고_입고_판매_${currentYear}년${currentMonth}월.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    showToast('엑셀 파일 다운로드 완료!', 'success');
}

// ========================================
// 이벤트 리스너
// ========================================

// 로그인 폼 제출
elements.loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const userId = elements.userIdInput.value.trim();
    const userPw = elements.userPwInput.value;

    if (!userId || !userPw) {
        showToast('아이디와 비밀번호를 입력해주세요.', 'error');
        return;
    }

    // 로그인 정보를 localStorage에 저장 (다른 탭에서 사용)
    localStorage.setItem('coupang_user_id', userId);
    localStorage.setItem('coupang_user_pw', userPw);

    // 저장된 기록 로드 및 대시보드 표시
    loadHistory();

    // 기록이 있으면 최신 날짜로 이동
    const dates = Object.keys(stockHistory);
    if (dates.length > 0) {
        const latestDate = dates.sort().pop();
        const [year, month] = latestDate.split('-');
        currentYear = parseInt(year);
        currentMonth = parseInt(month);
    }

    updatePeriodLabel();
    renderPivotTable();
    updateStats();
    showResult();

    showToast('로그인 완료! 데이터 수집 버튼을 눌러 데이터를 업데이트하세요.', 'success');
});

// 저장된 기록 보기
elements.viewHistoryBtn.addEventListener('click', () => {
    loadHistory();
    const dates = Object.keys(stockHistory);

    if (dates.length === 0) {
        showToast('저장된 기록이 없습니다.', 'info');
        return;
    }

    const latestDate = dates.sort().pop();
    const [year, month] = latestDate.split('-');
    currentYear = parseInt(year);
    currentMonth = parseInt(month);

    updatePeriodLabel();
    renderPivotTable();
    updateStats();
    showResult();
});

// 새로 조회 버튼
elements.newFetchBtn.addEventListener('click', () => {
    showLogin();
});

// 엑셀 다운로드 버튼
elements.downloadBtn.addEventListener('click', downloadExcel);

// 다시 시도 버튼
elements.retryBtn.addEventListener('click', () => {
    showLogin();
});

// 월 이동 버튼
elements.prevMonthBtn.addEventListener('click', goToPrevMonth);
elements.nextMonthBtn.addEventListener('click', goToNextMonth);

// 매핑 버튼 (동적으로 추가될 수 있음)
document.addEventListener('click', (e) => {
    if (e.target.id === 'mappingBtn' || e.target.closest('#mappingBtn')) {
        showMappingModal(true);
    }
});


// 초기화
loadHistory();
console.log('🚀 쿠팡 재고 대시보드 복구 완료 (입고/재고/판매 버전)');

// ========================================
// 로켓발주 탭 기능
// ========================================
const MARGIN_STORAGE_KEY = 'coupang_margin_data';
const EXPENSE_STORAGE_KEY = 'coupang_expense_data';
let marginData = {};  // 날짜별 수입(사입비) 데이터 { "2026-02-08": [{description, amount}] }
let expenseData = {}; // 날짜별 비용 데이터 { "2026-02-08": [{description, amount, note}] }
let marginYear = new Date().getFullYear();
let marginMonth = new Date().getMonth() + 1;
// 증빙일 기준 표 전용 월 (독립적으로 변경 가능)
let evidenceYear = new Date().getFullYear();
let evidenceMonth = new Date().getMonth() + 1;

// 마진 관련 DOM 요소 (동적 바인딩)
const marginElements = {
    get marginTab() { return document.getElementById('marginTab'); },
    get marginPeriodLabel() { return document.getElementById('marginPeriodLabel'); },
    get addItemModal() { return document.getElementById('addItemModal'); },
    get itemDate() { return document.getElementById('itemDate'); },
    get itemType() { return document.getElementById('itemType'); },
    get itemDescription() { return document.getElementById('itemDescription'); },
    get itemAmount() { return document.getElementById('itemAmount'); }
};

// 마진 데이터 로드
function loadMarginData() {
    try {
        const saved = localStorage.getItem(MARGIN_STORAGE_KEY);
        if (saved) {
            marginData = JSON.parse(saved);
        }
        const savedExpense = localStorage.getItem(EXPENSE_STORAGE_KEY);
        if (savedExpense) {
            expenseData = JSON.parse(savedExpense);
        }
    } catch (e) {
        console.error('마진 데이터 로드 실패:', e);
        marginData = {};
        expenseData = {};
    }
}

// 마진 데이터 저장
function saveMarginData() {
    try {
        localStorage.setItem(MARGIN_STORAGE_KEY, JSON.stringify(marginData));
        localStorage.setItem(EXPENSE_STORAGE_KEY, JSON.stringify(expenseData));
    } catch (e) {
        console.error('마진 데이터 저장 실패:', e);
    }
}

// 탭 전환
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('tab-btn')) {
        const tabName = e.target.dataset.tab;

        // 탭 버튼 활성화
        document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
        e.target.classList.add('active');

        // 탭 컨텐츠 전환
        document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

        // 해당 탭 컨텐츠 활성화
        const targetContent = document.getElementById(tabName + 'Tab');
        if (targetContent) {
            targetContent.classList.add('active');
        }

        // 탭별 추가 로직
        if (tabName === 'dashboard') {
            if (typeof renderDashboard === 'function') renderDashboard();
        } else if (tabName === 'margin') {
            loadCachedDeductionAndRender();
        } else if (tabName === 'ad') {
            if (typeof renderAdTab === 'function') setTimeout(renderAdTab, 0);
        } else if (tabName === 'stock') {
            if (typeof renderPivotTable === 'function') renderPivotTable();
            if (typeof updateStats === 'function') updateStats();
        } else if (tabName === 'deduction') {
            if (typeof renderDeductionTable === 'function') renderDeductionTable();
        }
    }
});

// ========================================
// 로켓발주 렌더링 함수들
// ========================================

// 백엔드 캐시 데이터 로드 후 렌더링
let rocketDataLoaded = false;
async function loadCachedDeductionAndRender() {
    // 이미 deductionData에 데이터가 있으면 바로 렌더링
    if (deductionData && deductionData.length > 0) {
        if (!rocketDataLoaded) {
            autoDetectMarginMonth();
            rocketDataLoaded = true;
        }
        renderRocketTab();
        return;
    }
    // localStorage에도 없으면 백엔드에서 가져오기
    try {
        const res = await fetch(`${REMOTE_API}/api/cached-deduction`);
        const result = await res.json();
        if (result.success && result.data && result.data.length > 0) {
            deductionData = result.data;
            deductionHistory = result.data;
            deductionHeaders = result.data.length > 0 ? Object.keys(result.data[0]).filter(k => !k.startsWith('_')) : [];
            // localStorage에도 저장
            if (typeof saveDeductionData === 'function') saveDeductionData();
            showToast(`정산 데이터 ${deductionData.length}건 로드 완료`, 'success');
        }
    } catch (e) {
        console.log('백엔드 캐시 로드 실패 (오프라인 모드):', e);
    }
    if (!rocketDataLoaded) {
        autoDetectMarginMonth();
        rocketDataLoaded = true;
    }
    renderRocketTab();
}

// deductionData에서 정산일이 가장 많은 달을 자동 감지
function autoDetectMarginMonth() {
    if (!deductionData || deductionData.length === 0) return;
    const monthCounts = {};
    deductionData.forEach(row => {
        const d = row['정산일'] || '';
        if (d) {
            const ym = d.substring(0, 7); // "YYYY-MM"
            monthCounts[ym] = (monthCounts[ym] || 0) + 1;
        }
    });
    let bestMonth = '';
    let bestCount = 0;
    Object.keys(monthCounts).forEach(ym => {
        if (monthCounts[ym] > bestCount) {
            bestCount = monthCounts[ym];
            bestMonth = ym;
        }
    });
    if (bestMonth) {
        const parts = bestMonth.split('-');
        marginYear = parseInt(parts[0]);
        marginMonth = parseInt(parts[1]);
    }
    // 증빙일은 현재 달의 2달 전으로 고정
    const now = new Date();
    let evM = now.getMonth() + 1 - 2; // 현재 달 - 2
    let evY = now.getFullYear();
    if (evM < 1) { evM += 12; evY--; }
    evidenceYear = evY;
    evidenceMonth = evM;
}

// 증빙일 표 월 이동
document.addEventListener('click', (e) => {
    if (e.target.id === 'evidencePrevMonthBtn') {
        evidenceMonth--;
        if (evidenceMonth < 1) { evidenceMonth = 12; evidenceYear--; }
        renderEvidenceDateTable();
    } else if (e.target.id === 'evidenceNextMonthBtn') {
        evidenceMonth++;
        if (evidenceMonth > 12) { evidenceMonth = 1; evidenceYear++; }
        renderEvidenceDateTable();
    }
});

// 전체 탭 렌더링
function renderRocketTab() {
    try { renderEvidenceDateTable(); } catch(e) { console.error('증빙일 테이블 렌더 에러:', e); }
    renderIncomeSection();
    renderExpenseSection();
}

// 마진 월 표시 업데이트
function updateMarginPeriodLabel() {
    if (marginElements.marginPeriodLabel) {
        marginElements.marginPeriodLabel.textContent = `${marginYear}년 ${marginMonth}월`;
    }
}

// 마진 월 이동
document.addEventListener('click', (e) => {
    if (e.target.id === 'marginPrevMonthBtn') {
        marginMonth--;
        if (marginMonth < 1) {
            marginMonth = 12;
            marginYear--;
        }
        renderRocketTab();
    } else if (e.target.id === 'marginNextMonthBtn') {
        marginMonth++;
        if (marginMonth > 12) {
            marginMonth = 1;
            marginYear++;
        }
        renderRocketTab();
    }
});

// ── 유틸: 해당 월의 날짜 수 ──
function getDaysInMonth(year, month) {
    return new Date(year, month, 0).getDate();
}

// ── 유틸: 날짜 포맷 YYYY.M.D ──
function formatDateDot(year, month, day) {
    return `${year}.${month}.${day}`;
}

// ── 유틸: 날짜 포맷 YYYY-MM-DD ──
function formatDateISO(year, month, day) {
    return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

// ── 각 섹션 합계 계산 함수 (렌더링 없이 계산만) ──

// 정산일 기준 정산액 합계
function getSettlementTotal() {
    const monthPrefix = `${marginYear}-${String(marginMonth).padStart(2, '0')}`;
    let total = 0;
    if (typeof deductionData !== 'undefined' && deductionData && deductionData.length > 0) {
        deductionData.forEach(row => {
            const settlementDate = row['정산일'] || '';
            const amountStr = row['정산금액'] || row['지급액'] || row['공제후 지급액'] || '';
            if (settlementDate.startsWith(monthPrefix)) {
                total += parseInt(amountStr.replace(/[^0-9-]/g, '')) || 0;
            }
        });
    }
    return total;
}

// 증빙일 기준 정산액 합계
function getReceivingTotal() {
    const monthPrefix = `${marginYear}-${String(marginMonth).padStart(2, '0')}`;
    let total = 0;
    if (typeof deductionData !== 'undefined' && deductionData && deductionData.length > 0) {
        deductionData.forEach(row => {
            const dateCol = row['증빙일'] || row['매출발생일'] || '';
            const amountStr = row['정산금액'] || row['지급액'] || row['공제후 지급액'] || '';
            if (dateCol.startsWith(monthPrefix)) {
                total += parseInt(amountStr.replace(/[^0-9-]/g, '')) || 0;
            }
        });
    }
    return total;
}

function getAdCostTotal() {
    const monthPrefix = `${marginYear}-${String(marginMonth).padStart(2, '0')}`;
    let total = 0;
    if (typeof adHistory !== 'undefined' && adHistory) {
        Object.keys(adHistory).forEach(dateStr => {
            if (dateStr.startsWith(monthPrefix)) {
                total += adHistory[dateStr].ad_cost || 0;
            }
        });
    }
    return total;
}

// 다음달 광고비 합계 (증빙일 기준 테이블용)
function getNextMonthAdCostTotal() {
    let nextMonth = marginMonth + 1;
    let nextYear = marginYear;
    if (nextMonth > 12) { nextMonth = 1; nextYear++; }
    const monthPrefix = `${nextYear}-${String(nextMonth).padStart(2, '0')}`;
    let total = 0;
    if (typeof adHistory !== 'undefined' && adHistory) {
        Object.keys(adHistory).forEach(dateStr => {
            if (dateStr.startsWith(monthPrefix)) {
                total += adHistory[dateStr].ad_cost || 0;
            }
        });
    }
    return total;
}

function getIncomeTotal() {
    const monthPrefix = `${marginYear}-${String(marginMonth).padStart(2, '0')}`;
    let total = 0;
    Object.keys(marginData).forEach(date => {
        if (date.startsWith(monthPrefix)) {
            marginData[date].forEach(item => {
                total += Math.abs(item.amount);
            });
        }
    });
    return total;
}

function getExpenseTotal() {
    const monthPrefix = `${marginYear}-${String(marginMonth).padStart(2, '0')}`;
    let total = 0;
    Object.keys(expenseData).forEach(date => {
        if (date.startsWith(monthPrefix)) {
            expenseData[date].forEach(item => {
                total += Math.abs(item.amount);
            });
        }
    });
    return total;
}

// ── 유틸: 날짜별 데이터 맵 생성 ──
function buildDateMap_settlement(year, month) {
    // 정산일 기준으로 deductionData에서 해당 월 데이터 추출
    const monthPrefix = `${year}-${String(month).padStart(2, '0')}`;
    const map = {}; // { day: totalAmount }
    if (typeof deductionData !== 'undefined' && deductionData && deductionData.length > 0) {
        deductionData.forEach(row => {
            const settlementDate = row['정산일'] || '';
            if (settlementDate.startsWith(monthPrefix)) {
                const day = parseInt(settlementDate.split('-')[2]) || 0;
                if (day > 0) {
                    const amountStr = row['정산금액'] || row['지급액'] || row['공제후 지급액'] || '';
                    const amount = parseInt(amountStr.replace(/[^0-9-]/g, '')) || 0;
                    map[day] = (map[day] || 0) + amount;
                }
            }
        });
    }
    return map;
}

function buildDateMap_evidence(year, month) {
    // 증빙일 기준으로 deductionData에서 해당 월 데이터 추출
    // map = { day: { amount, settlementDates: Set } }
    const monthPrefix = `${year}-${String(month).padStart(2, '0')}`;
    const map = {};
    if (typeof deductionData !== 'undefined' && deductionData && deductionData.length > 0) {
        deductionData.forEach(row => {
            const evidenceDate = row['증빙일'] || row['매출발생일'] || '';
            if (evidenceDate.startsWith(monthPrefix)) {
                const day = parseInt(evidenceDate.split('-')[2]) || 0;
                if (day > 0) {
                    const amountStr = row['정산금액'] || row['지급액'] || row['공제후 지급액'] || '';
                    const amount = parseInt(amountStr.replace(/[^0-9-]/g, '')) || 0;
                    if (!map[day]) {
                        map[day] = { amount: 0, settlementDates: new Set() };
                    }
                    map[day].amount += amount;
                    const sd = row['정산일'] || '';
                    if (sd) map[day].settlementDates.add(sd);
                }
            }
        });
    }
    return map;
}

function buildDateMap_adCost(year, month) {
    const monthPrefix = `${year}-${String(month).padStart(2, '0')}`;
    const map = {};
    if (typeof adHistory !== 'undefined' && adHistory) {
        Object.keys(adHistory).forEach(dateStr => {
            if (dateStr.startsWith(monthPrefix)) {
                const day = parseInt(dateStr.split('-')[2]) || 0;
                if (day > 0) {
                    map[day] = (map[day] || 0) + (adHistory[dateStr].ad_cost || 0);
                }
            }
        });
    }
    return map;
}

function buildDateMap_income(year, month) {
    const monthPrefix = `${year}-${String(month).padStart(2, '0')}`;
    const map = {};
    Object.keys(marginData).forEach(date => {
        if (date.startsWith(monthPrefix)) {
            const day = parseInt(date.split('-')[2]) || 0;
            if (day > 0) {
                let dayTotal = 0;
                marginData[date].forEach(item => { dayTotal += Math.abs(item.amount); });
                map[day] = (map[day] || 0) + dayTotal;
            }
        }
    });
    return map;
}

function buildDateMap_expense(year, month) {
    const monthPrefix = `${year}-${String(month).padStart(2, '0')}`;
    const map = {};
    Object.keys(expenseData).forEach(date => {
        if (date.startsWith(monthPrefix)) {
            const day = parseInt(date.split('-')[2]) || 0;
            if (day > 0) {
                let dayTotal = 0;
                expenseData[date].forEach(item => { dayTotal += Math.abs(item.amount); });
                map[day] = (map[day] || 0) + dayTotal;
            }
        }
    });
    return map;
}

// ── 📅 Table 1: 정산일 기준 테이블 렌더링 ──
function renderSettlementDateTable() {
    const thead = document.getElementById('settlementDateHead');
    const tbody = document.getElementById('settlementDateBody');
    const tfoot = document.getElementById('settlementDateFoot');
    if (!thead || !tbody || !tfoot) return;

    const m = marginMonth;
    const y = marginYear;
    const daysInMonth = getDaysInMonth(y, m);
    let setM = m + 2, setY = y;
    if (setM > 12) { setM -= 12; setY++; }

    // 헤더
    thead.innerHTML = `<tr>
        <th>날짜</th>
        <th style="text-align:right;">${m}월 증빙(${setM}월 정산)</th>
        <th style="text-align:right;">${m}월 광고비</th>
        <th style="text-align:right;">${m}월 수입</th>
        <th style="text-align:right;">${m}월 비용</th>
    </tr>`;

    // 데이터 맵 생성
    const settlementMap = buildDateMap_settlement(y, m);
    const adCostMap = buildDateMap_adCost(y, m);
    const incomeMap = buildDateMap_income(y, m);
    const expenseMap = buildDateMap_expense(y, m);

    let totalSettlement = 0, totalAd = 0, totalIncome = 0, totalExpense = 0;
    let html = '';

    for (let d = 1; d <= daysInMonth; d++) {
        const sVal = settlementMap[d] || 0;
        const aVal = adCostMap[d] || 0;
        const iVal = incomeMap[d] || 0;
        const eVal = expenseMap[d] || 0;

        totalSettlement += sVal;
        totalAd += aVal;
        totalIncome += iVal;
        totalExpense += eVal;

        const hasData = sVal || aVal || iVal || eVal;

        html += `<tr${hasData ? '' : ' class="empty-row"'}>
            <td>${formatDateDot(y, m, d)}</td>
            <td style="text-align:right;${sVal ? ' color:var(--success); font-weight:500;' : ''}">${sVal ? sVal.toLocaleString() : ''}</td>
            <td style="text-align:right;${aVal ? ' color:var(--danger); font-weight:500;' : ''}">${aVal ? aVal.toLocaleString() : ''}</td>
            <td style="text-align:right;${iVal ? ' color:var(--danger); font-weight:500;' : ''}">${iVal ? iVal.toLocaleString() : ''}</td>
            <td style="text-align:right;${eVal ? ' color:var(--danger); font-weight:500;' : ''}">${eVal ? eVal.toLocaleString() : ''}</td>
        </tr>`;
    }
    tbody.innerHTML = html;

    const totalProfit = totalSettlement - totalAd - totalIncome - totalExpense;
    const profitColor = totalProfit >= 0 ? 'var(--success)' : 'var(--danger)';

    tfoot.innerHTML = `
        <tr style="font-weight:bold; border-top:2px solid var(--primary);">
            <td>합계</td>
            <td style="text-align:right; color:var(--success);">${totalSettlement.toLocaleString()}</td>
            <td style="text-align:right; color:var(--danger);">${totalAd.toLocaleString()}</td>
            <td style="text-align:right; color:var(--danger);">${totalIncome.toLocaleString()}</td>
            <td style="text-align:right; color:var(--danger);">${totalExpense.toLocaleString()}</td>
        </tr>
        <tr style="font-weight:bold; background:var(--bg-tertiary);">
            <td>총 이익</td>
            <td colspan="4" style="text-align:right; color:${profitColor}; font-size:1.05rem;">${totalProfit >= 0 ? '+' : ''}${totalProfit.toLocaleString()}원</td>
        </tr>`;
}

// ── 📋 Table 2: 증빙일 기준 테이블 렌더링 ──
// 증빙일 = evidenceMonth, 광고비 = evidenceMonth+1
function renderEvidenceDateTable() {
    const thead = document.getElementById('evidenceDateHead');
    const tbody = document.getElementById('evidenceDateBody');
    const tfoot = document.getElementById('evidenceDateFoot');
    if (!thead || !tbody || !tfoot) return;

    const evM = evidenceMonth;
    const evY = evidenceYear;

    // 광고비는 증빙일 다음달
    let adMonth = evM + 1;
    let adYear = evY;
    if (adMonth > 12) { adMonth = 1; adYear++; }

    // 라벨 업데이트
    const labelEl = document.getElementById('evidencePeriodLabel');
    if (labelEl) labelEl.textContent = `${evY}년 ${evM}월`;

    const daysInEvMonth = getDaysInMonth(evY, evM);
    const daysInAdMonth = getDaysInMonth(adYear, adMonth);
    const maxDays = Math.max(daysInEvMonth, daysInAdMonth);

    // 헤더
    let setM2 = evM + 2, setY2 = evY;
    if (setM2 > 12) { setM2 -= 12; setY2++; }
    thead.innerHTML = `<tr>
        <th>날짜</th>
        <th style="text-align:right;">${evM}월 증빙(${setM2}월 정산)</th>
        <th style="text-align:right;">${evM}월 수입</th>
        <th style="text-align:right;">${evM}월 비용</th>
        <th style="border-left:2px solid var(--border-color);">날짜</th>
        <th style="text-align:right;">${adMonth}월 광고비</th>
    </tr>`;

    // 데이터 맵 생성: 정산/수입/비용은 증빙일 월, 광고비는 다음달
    const evidenceMap = buildDateMap_evidence(evY, evM);
    const incomeMap = buildDateMap_income(evY, evM);
    const expenseMap = buildDateMap_expense(evY, evM);
    const adCostMap = buildDateMap_adCost(adYear, adMonth);

    let totalEvidence = 0, totalIncome = 0, totalExpense = 0, totalAd = 0;
    let html = '';

    for (let d = 1; d <= maxDays; d++) {
        const eData = d <= daysInEvMonth ? (evidenceMap[d] || null) : null;
        const eVal = eData ? eData.amount : 0;
        const iVal = d <= daysInEvMonth ? (incomeMap[d] || 0) : 0;
        const exVal = d <= daysInEvMonth ? (expenseMap[d] || 0) : 0;
        const aVal = d <= daysInAdMonth ? (adCostMap[d] || 0) : 0;

        totalEvidence += eVal;
        totalIncome += iVal;
        totalExpense += exVal;
        totalAd += aVal;

        const hasLeft = eVal || iVal || exVal;
        const hasRight = aVal;

        // 증빙일/정산일 함께 표기
        let dateLabel = '';
        if (d <= daysInEvMonth) {
            const evDate = formatDateISO(evY, evM, d);
            if (eData && eData.settlementDates.size > 0) {
                const sdArr = [...eData.settlementDates].sort();
                dateLabel = sdArr.map(sd => `${evDate}/${sd}`).join('<br>');
            } else {
                dateLabel = evDate;
            }
        }

        html += `<tr${(!hasLeft && !hasRight) ? ' class="empty-row"' : ''}>
            <td style="font-size:0.75rem;">${dateLabel}</td>
            <td style="text-align:right;${eVal ? ' color:var(--success); font-weight:500;' : ''}">${eVal ? eVal.toLocaleString() : ''}</td>
            <td style="text-align:right;${iVal ? ' color:var(--danger); font-weight:500;' : ''}">${iVal ? iVal.toLocaleString() : ''}</td>
            <td style="text-align:right;${exVal ? ' color:var(--danger); font-weight:500;' : ''}">${exVal ? exVal.toLocaleString() : ''}</td>
            <td style="border-left:2px solid var(--border-color);">${d <= daysInAdMonth ? formatDateDot(adYear, adMonth, d) : ''}</td>
            <td style="text-align:right;${aVal ? ' color:var(--danger); font-weight:500;' : ''}">${aVal ? aVal.toLocaleString() : ''}</td>
        </tr>`;
    }
    tbody.innerHTML = html;

    const totalProfit = totalEvidence - totalAd - totalIncome - totalExpense;
    const profitColor = totalProfit >= 0 ? 'var(--success)' : 'var(--danger)';

    tfoot.innerHTML = `
        <tr style="font-weight:bold; border-top:2px solid var(--primary);">
            <td>합계</td>
            <td style="text-align:right; color:var(--success);">${totalEvidence.toLocaleString()}</td>
            <td style="text-align:right; color:var(--danger);">${totalIncome.toLocaleString()}</td>
            <td style="text-align:right; color:var(--danger);">${totalExpense.toLocaleString()}</td>
            <td style="border-left:2px solid var(--border-color);">합계</td>
            <td style="text-align:right; color:var(--danger);">${totalAd.toLocaleString()}</td>
        </tr>
        <tr style="font-weight:bold; background:var(--bg-tertiary);">
            <td>총 이익</td>
            <td colspan="5" style="text-align:right; color:${profitColor}; font-size:1.05rem;">${totalProfit >= 0 ? '+' : ''}${totalProfit.toLocaleString()}원</td>
        </tr>`;
}

// ── 💸 수입내역 (사입비) 섹션 렌더링 ──
function renderIncomeSection() {
    const tbody = document.getElementById('rocketIncomeBody');
    const sumEl = document.getElementById('rocketIncomeSum');
    if (!tbody) return;

    const monthPrefix = `${marginYear}-${String(marginMonth).padStart(2, '0')}`;
    let total = 0;
    let allItems = [];

    Object.keys(marginData).forEach(date => {
        if (date.startsWith(monthPrefix)) {
            marginData[date].forEach((item, index) => {
                const amount = Math.abs(item.amount);
                total += amount;
                allItems.push({ date, description: item.description, amount, index });
            });
        }
    });

    allItems.sort((a, b) => a.date.localeCompare(b.date));

    if (allItems.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; padding:20px; color:var(--text-muted);">항목을 추가해주세요</td></tr>';
    } else {
        let html = '';
        allItems.forEach(item => {
            html += `<tr>
                <td>${item.date}</td>
                <td>${escapeHtml(item.description || '-')}</td>
                <td style="text-align:right; color:var(--danger);">-${item.amount.toLocaleString()}원</td>
                <td><button class="delete-btn" data-date="${item.date}" data-index="${item.index}" data-type="income">🗑️</button></td>
            </tr>`;
        });
        tbody.innerHTML = html;
    }

    if (sumEl) sumEl.textContent = `-${total.toLocaleString()}원`;
}

// ── 💸 비용내역 섹션 렌더링 ──
function renderExpenseSection() {
    const tbody = document.getElementById('rocketExpenseBody');
    const sumEl = document.getElementById('rocketExpenseSum');
    if (!tbody) return;

    const monthPrefix = `${marginYear}-${String(marginMonth).padStart(2, '0')}`;
    let total = 0;
    let allItems = [];

    Object.keys(expenseData).forEach(date => {
        if (date.startsWith(monthPrefix)) {
            expenseData[date].forEach((item, index) => {
                const amount = Math.abs(item.amount);
                total += amount;
                allItems.push({ date, description: item.description, amount, note: item.note || '', index });
            });
        }
    });

    allItems.sort((a, b) => a.date.localeCompare(b.date));

    if (allItems.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:20px; color:var(--text-muted);">비용을 추가해주세요</td></tr>';
    } else {
        let html = '';
        allItems.forEach(item => {
            html += `<tr>
                <td>${item.date}</td>
                <td>${escapeHtml(item.description || '-')}</td>
                <td style="text-align:right; color:var(--danger);">-${item.amount.toLocaleString()}원</td>
                <td>${escapeHtml(item.note)}</td>
                <td><button class="delete-btn" data-date="${item.date}" data-index="${item.index}" data-type="expense">🗑️</button></td>
            </tr>`;
        });
        tbody.innerHTML = html;
    }

    if (sumEl) sumEl.textContent = `-${total.toLocaleString()}원`;
}

// ── 상단 요약 카드 업데이트 ──
function updateRocketSummary() {
    const settlement = getSettlementTotal();
    const adCost = getAdCostTotal();
    const income = getIncomeTotal();
    const expense = getExpenseTotal();
    const profit = settlement - adCost - income - expense;

    const el = (id) => document.getElementById(id);
    if (el('rocketReceivingTotal')) el('rocketReceivingTotal').textContent = `${settlement.toLocaleString()}원`;
    if (el('rocketAdCostTotal')) el('rocketAdCostTotal').textContent = `-${adCost.toLocaleString()}원`;
    if (el('rocketIncomeTotal')) el('rocketIncomeTotal').textContent = `-${income.toLocaleString()}원`;
    if (el('rocketExpenseTotal')) el('rocketExpenseTotal').textContent = `-${expense.toLocaleString()}원`;
    if (el('rocketProfitTotal')) {
        el('rocketProfitTotal').textContent = `${profit >= 0 ? '+' : ''}${profit.toLocaleString()}원`;
        el('rocketProfitTotal').style.color = profit >= 0 ? 'var(--success)' : 'var(--danger)';
    }
}

// 정산 조회 버튼
document.addEventListener('click', async (e) => {
    if (e.target.id === 'fetchSettlementBtn' || e.target.closest('#fetchSettlementBtn')) {
        const { userId, userPw } = getCredentials();

        if (!userId || !userPw) {
            showToast('먼저 재고 탭에서 로그인해주세요.', 'error');
            return;
        }

        showToast('정산 데이터 조회 중...', 'info');

        try {
            const result = await fetchDeductionDataWithBuffer(userId, userPw);
            if (result.success) {
                if (result.count > 0) {
                    showToast(`정산 데이터 ${result.count}건 갱신 완료!`, 'success');
                } else {
                    showToast('새로운 정산 데이터가 없습니다.', 'info');
                }
            } else {
                showToast('정산 조회 실패', 'error');
            }
        } catch (error) {
            console.error('정산 조회 에러:', error);
            showToast('정산 조회 중 오류 발생', 'error');
        }
    }
});

// ── 일회용: 전체 수집 (2025.4~) 버튼 - 나중에 이 블록만 삭제하면 됨 ──
document.addEventListener('click', async (e) => {
    if (e.target.id === 'fetchFullDeductionBtn' || e.target.closest('#fetchFullDeductionBtn')) {
        const { userId, userPw } = getCredentials();
        if (!userId || !userPw) {
            showToast('먼저 재고 탭에서 로그인해주세요.', 'error');
            return;
        }
        if (!confirm('2025년 4월부터 전체 정산 데이터를 수집합니다.\n시간이 오래 걸릴 수 있습니다. 진행할까요?')) return;

        const btn = document.getElementById('fetchFullDeductionBtn');
        if (btn) { btn.disabled = true; btn.textContent = '수집 중...'; }
        showToast('전체 정산 데이터 수집 중... (2025.4~)', 'info');

        try {
            console.log('📡 전체 수집 요청 시작:', `${API_BASE_URL}/api/fetch-deduction`);
            const res = await fetch(`${API_BASE_URL}/api/fetch-deduction`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, user_pw: userPw, start_year: 2025, start_month: 4 })
            });
            console.log('📡 서버 응답 상태:', res.status);
            const result = await res.json();
            console.log('📡 서버 응답 데이터:', JSON.stringify(result).substring(0, 500));
            if (result.success && result.data && result.data.length > 0) {
                // 기존 데이터와 병합 (중복 제거)
                const getKey = (r) => `${r['계산서 번호']}_${r['증빙일']}_${r['정산금액']}`;
                const existingKeys = new Set(deductionData.map(getKey));
                let newCount = 0;
                result.data.forEach(row => {
                    if (row['계산서 번호'] && !existingKeys.has(getKey(row))) {
                        deductionData.push(row);
                        existingKeys.add(getKey(row));
                        newCount++;
                    }
                });
                deductionHistory = deductionData;
                deductionHeaders = deductionData.length > 0 ? Object.keys(deductionData[0]).filter(k => !k.startsWith('_')) : [];
                if (typeof saveDeductionData === 'function') saveDeductionData();
                renderDeductionTable();
                renderRocketTab();
                showToast(`전체 수집 완료! 신규 ${newCount}건 추가 (총 ${deductionData.length}건)`, 'success');
            } else {
                const errMsg = result.error || result.message || '데이터가 0건입니다';
                console.error('❌ 전체 수집 실패:', errMsg);
                showToast('전체 수집 실패: ' + errMsg, 'error');
            }
        } catch (error) {
            console.error('❌ 전체 수집 에러:', error);
            showToast('전체 수집 중 오류 발생: ' + error.message, 'error');
        }
        if (btn) { btn.disabled = false; btn.innerHTML = '<span>📥</span> 전체 수집 (2025.4~)'; }
    }
});
// ── 일회용 블록 끝 ──

// 항목 추가 모달 열기 (수입)
document.addEventListener('click', (e) => {
    if (e.target.id === 'addItemBtn' || e.target.closest('#addItemBtn') || e.target.id === 'addItemBtnTop' || e.target.closest('#addItemBtnTop')) {
        if (marginElements.addItemModal) {
            marginElements.addItemModal.dataset.mode = 'income';
            marginElements.addItemModal.classList.remove('hidden');
            if (marginElements.itemDate) {
                marginElements.itemDate.value = new Date().toISOString().split('T')[0];
            }
            const modalTitle = marginElements.addItemModal.querySelector('h3');
            if (modalTitle) modalTitle.textContent = '항목 추가';
        }
    }
});

// 항목 추가 모달 닫기
document.addEventListener('click', (e) => {
    if (e.target.id === 'closeAddItemModal' || e.target.id === 'cancelAddItem') {
        if (marginElements.addItemModal) {
            marginElements.addItemModal.classList.add('hidden');
        }
    }
});

// ── 한 줄 파싱 입력 ──
function parseQuickInput(text) {
    text = text.trim();
    if (!text) return null;

    let date = new Date().toISOString().split('T')[0];
    let remaining = text;

    // 날짜 파싱: 맨 앞의 "어제", "그제", "M/D", "M월D일"
    const datePatterns = [
        { regex: /^어제\s+/, fn: () => { const d = new Date(); d.setDate(d.getDate() - 1); return d; }},
        { regex: /^그제\s+/, fn: () => { const d = new Date(); d.setDate(d.getDate() - 2); return d; }},
        { regex: /^(\d{1,2})\/(\d{1,2})\s+/, fn: (m) => new Date(new Date().getFullYear(), parseInt(m[1]) - 1, parseInt(m[2]))},
        { regex: /^(\d{1,2})월\s*(\d{1,2})일?\s+/, fn: (m) => new Date(new Date().getFullYear(), parseInt(m[1]) - 1, parseInt(m[2]))},
    ];

    for (const p of datePatterns) {
        const match = remaining.match(p.regex);
        if (match) {
            const d = p.fn(match);
            date = d.toISOString().split('T')[0];
            remaining = remaining.replace(match[0], '');
            break;
        }
    }

    // 금액 파싱: 맨 뒤의 숫자+단위 (만, 천, 원)
    // "3만원", "2만5천원", "15000", "10만", "5천원", "2만5천"
    const amountRegex = /(\d+만\s*\d*천?\s*\d*원?|\d+천\s*\d*원?|\d+원|\d+)\s*$/;
    const amountMatch = remaining.match(amountRegex);
    if (!amountMatch) return null;

    const amountStr = amountMatch[1].replace(/\s/g, '');
    let amount = 0;

    const manMatch = amountStr.match(/(\d+)만/);
    const cheonMatch = amountStr.match(/(\d+)천/);
    const plainMatch = amountStr.replace(/만|천|원/g, '').match(/\d+$/);

    if (manMatch) amount += parseInt(manMatch[1]) * 10000;
    if (cheonMatch) amount += parseInt(cheonMatch[1]) * 1000;
    if (!manMatch && !cheonMatch && plainMatch) {
        amount = parseInt(plainMatch[0]);
    } else if ((manMatch || cheonMatch) && plainMatch && plainMatch[0] !== (manMatch?.[1] || '') && plainMatch[0] !== (cheonMatch?.[1] || '')) {
        // "2만5천500" 같은 경우 남은 숫자 처리
        const leftover = parseInt(plainMatch[0]);
        if (leftover < 1000) amount += leftover;
    }

    if (amount <= 0) return null;

    // 내역: 금액 부분 제거 후 남은 텍스트
    const description = remaining.replace(amountRegex, '').trim();
    if (!description) return null;

    return { date, description, amount };
}

// 빠른 입력 처리 함수
function handleQuickAdd(inputEl, mode) {
    const parsed = parseQuickInput(inputEl.value);
    if (!parsed) {
        showToast('입력 형식: 내역 금액 (예: 포장재 3만원)', 'error');
        return;
    }

    const { date, description, amount } = parsed;

    if (mode === 'expense') {
        if (!expenseData[date]) expenseData[date] = [];
        expenseData[date].push({ description, amount: -amount, note: '' });
    } else {
        if (!marginData[date]) marginData[date] = [];
        marginData[date].push({ type: '매입', description, amount: -amount });
    }

    // 현재 보고 있는 월과 동기화
    const addedMonth = parseInt(date.split('-')[1]);
    const addedYear = parseInt(date.split('-')[0]);
    marginYear = addedYear;
    marginMonth = addedMonth;

    saveMarginData();
    renderRocketTab();
    inputEl.value = '';
    showToast(`${description} ${amount.toLocaleString()}원 추가 (${date})`, 'success');

    // 추가 버튼 효과
    const btn = inputEl.closest('.quick-input-bar')?.querySelector('.quick-add-btn');
    if (btn) successPop(btn);
}

function successPop(btn) {
    const orig = btn.textContent;
    btn.textContent = '\u2713';
    btn.classList.add('pop-success');
    setTimeout(() => {
        btn.textContent = orig;
        btn.classList.remove('pop-success');
    }, 600);
}

// 빠른 입력 이벤트: Enter 키
document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.target.classList.contains('quick-input')) {
        e.preventDefault();
        handleQuickAdd(e.target, e.target.dataset.mode);
    }
});

// 빠른 입력 이벤트: 추가 버튼 클릭
document.addEventListener('click', (e) => {
    const btn = e.target.closest('.quick-add-btn');
    if (btn) {
        const bar = btn.closest('.quick-input-bar');
        const inputEl = bar?.querySelector('.quick-input');
        if (inputEl) handleQuickAdd(inputEl, inputEl.dataset.mode);
    }
});

// 항목 추가 확인
document.addEventListener('click', (e) => {
    if (e.target.id === 'confirmAddItem') {
        const date = marginElements.itemDate?.value;
        const description = marginElements.itemDescription?.value;
        const amount = parseInt(marginElements.itemAmount?.value) || 0;
        const mode = marginElements.addItemModal?.dataset.mode || 'income';

        if (!date || !description || amount <= 0) {
            showToast('모든 항목을 입력해주세요.', 'error');
            return;
        }

        if (mode === 'expense') {
            // 비용 데이터에 추가
            if (!expenseData[date]) {
                expenseData[date] = [];
            }
            expenseData[date].push({
                description: description,
                amount: -amount,
                note: ''
            });
        } else {
            // 수입(사입비) 데이터에 추가
            if (!marginData[date]) {
                marginData[date] = [];
            }
            marginData[date].push({
                type: '매입',
                description: description,
                amount: -amount
            });
        }

        saveMarginData();
        renderRocketTab();

        // 모달 닫기 및 폼 초기화
        if (marginElements.addItemModal) {
            marginElements.addItemModal.classList.add('hidden');
            marginElements.addItemModal.dataset.mode = 'income';
        }
        if (marginElements.itemDescription) marginElements.itemDescription.value = '';
        if (marginElements.itemAmount) marginElements.itemAmount.value = '';

        showToast(mode === 'expense' ? '비용이 추가되었습니다.' : '항목이 추가되었습니다.', 'success');
        successPop(e.target);
    }
});

// 항목 삭제 (수입/비용 구분)
document.addEventListener('click', (e) => {
    const delBtn = e.target.closest('.delete-btn');
    if (delBtn) {
        const date = delBtn.dataset.date;
        const index = parseInt(delBtn.dataset.index);
        const type = delBtn.dataset.type;

        if (type === 'expense') {
            if (expenseData[date] && expenseData[date][index]) {
                expenseData[date].splice(index, 1);
                if (expenseData[date].length === 0) {
                    delete expenseData[date];
                }
                saveMarginData();
                renderRocketTab();
                showToast('비용이 삭제되었습니다.', 'success');
            }
        } else {
            if (marginData[date] && marginData[date][index]) {
                marginData[date].splice(index, 1);
                if (marginData[date].length === 0) {
                    delete marginData[date];
                }
                saveMarginData();
                renderRocketTab();
                showToast('항목이 삭제되었습니다.', 'success');
            }
        }
    }
});

// 비용 추가 버튼
document.addEventListener('click', (e) => {
    if (e.target.id === 'addExpenseBtn' || e.target.closest('#addExpenseBtn') || e.target.id === 'addExpenseBtnTop' || e.target.closest('#addExpenseBtnTop')) {
        if (marginElements.addItemModal) {
            // 모달 재사용 - 비용 모드로 표시
            marginElements.addItemModal.dataset.mode = 'expense';
            marginElements.addItemModal.classList.remove('hidden');
            if (marginElements.itemDate) {
                marginElements.itemDate.value = new Date().toISOString().split('T')[0];
            }
            // 모달 제목 변경
            const modalTitle = marginElements.addItemModal.querySelector('h3');
            if (modalTitle) modalTitle.textContent = '비용 추가';
        }
    }
});

// 마진 데이터 초기 로드
loadMarginData();
console.log('🚀 로켓발주 기능 로드 완료');



// ========================================
// 대시보드 탭
// ========================================

// 오늘 날짜를 YYYY-MM-DD 형식으로 반환
function getDashToday() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function getDashYesterday() {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

// 대시보드 날짜 입력값 초기화 (기본: 어제)
function initDashDates() {
    const startInput = document.getElementById('dashStartDate');
    const endInput = document.getElementById('dashEndDate');
    const yesterday = getDashYesterday();
    if (startInput && !startInput.value) startInput.value = yesterday;
    if (endInput && !endInput.value) endInput.value = yesterday;
}

// 날짜 변경 시 자동 렌더링 (수동 날짜 선택 시 버튼 활성화 해제)
document.addEventListener('change', (e) => {
    if (e.target.id === 'dashStartDate' || e.target.id === 'dashEndDate') {
        document.querySelectorAll('.dash-period-btn').forEach(btn => btn.classList.remove('active'));
        renderDashboard();
    }
});

// 대시보드 날짜 버튼 활성화 상태 업데이트
function updateDashPeriodBtnActive(activeId) {
    document.querySelectorAll('.dash-period-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    const activeBtn = document.getElementById(activeId);
    if (activeBtn) activeBtn.classList.add('active');
}

// 빠른 날짜 선택 버튼 이벤트
document.addEventListener('click', (e) => {
    const startInput = document.getElementById('dashStartDate');
    const endInput = document.getElementById('dashEndDate');
    if (!startInput || !endInput) return;

    if (e.target.id === 'dashYesterdayBtn' || e.target.closest('#dashYesterdayBtn')) {
        const yesterday = new Date();
        yesterday.setDate(yesterday.getDate() - 1);
        const yStr = `${yesterday.getFullYear()}-${String(yesterday.getMonth() + 1).padStart(2, '0')}-${String(yesterday.getDate()).padStart(2, '0')}`;
        startInput.value = yStr;
        endInput.value = yStr;
        updateDashPeriodBtnActive('dashYesterdayBtn');
        renderDashboard();
    } else if (e.target.id === 'dashTodayBtn' || e.target.closest('#dashTodayBtn')) {
        startInput.value = getDashToday();
        endInput.value = getDashToday();
        updateDashPeriodBtnActive('dashTodayBtn');
        renderDashboard();
    } else if (e.target.id === 'dashWeekBtn' || e.target.closest('#dashWeekBtn')) {
        const end = new Date();
        const start = new Date();
        start.setDate(start.getDate() - 6);
        startInput.value = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}-${String(start.getDate()).padStart(2, '0')}`;
        endInput.value = getDashToday();
        updateDashPeriodBtnActive('dashWeekBtn');
        renderDashboard();
    } else if (e.target.id === 'dashMonthBtn' || e.target.closest('#dashMonthBtn')) {
        const now = new Date();
        startInput.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`;
        endInput.value = getDashToday();
        updateDashPeriodBtnActive('dashMonthBtn');
        renderDashboard();
    }
});

/**
 * 대시보드 렌더링 - 날짜 범위 기반 상품별 요약 테이블
 */
function renderDashboard() {
    const tableBody = document.getElementById('dashboardTableBody');
    if (!tableBody) return;

    initDashDates();

    const startDate = document.getElementById('dashStartDate').value;
    const endDate = document.getElementById('dashEndDate').value;
    if (!startDate || !endDate) return;

    // 범위 내 날짜 필터 (stockHistory + adHistory 기준)
    const stockDates = Object.keys(stockHistory);
    const adDates = Object.keys(adHistory);
    const uniqueDates = [...new Set([...stockDates, ...adDates])].sort();
    const rangeDates = uniqueDates.filter(d => d >= startDate && d <= endDate);

    // 판매량 계산을 위해 시작일 전날 데이터도 필요
    const dayBeforeStart = uniqueDates.filter(d => d < startDate).pop(); // 시작일 직전 날짜

    // 계산용 날짜 = [전날] + 범위 내 날짜
    const calcDates = dayBeforeStart ? [dayBeforeStart, ...rangeDates] : rangeDates;

    // 1) 상품별 데이터 집계
    const productMap = {};

    // 상품명 정규화 (공백/특수문자 차이로 인한 중복 방지)
    function normalizeProductName(name) {
        // 광고 상품명에 붙는 "\nID : 숫자" 제거
        return name.replace(/\nID\s*:\s*\d+/g, '').replace(/\s+/g, ' ').trim();
    }

    // 광고 상품명 → 재고 상품명 매칭 (부분 문자열 매칭)
    function findMatchingProductKey(adName, productMap) {
        // 1) 정확히 일치
        if (productMap[adName]) return adName;

        // 2) 한쪽이 다른 쪽을 포함하는 경우
        const keys = Object.keys(productMap);
        for (const key of keys) {
            if (key.includes(adName) || adName.includes(key)) {
                return key;
            }
        }

        return null; // 매칭 실패 → 새 항목 생성
    }

    // 모든 상품 수집 (범위 내 날짜에서만)
    rangeDates.forEach(date => {
        const dayData = stockHistory[date];
        if (!dayData) return;
        dayData.forEach(item => {
            const normName = normalizeProductName(item.product_name);
            if (!productMap[normName]) {
                productMap[normName] = {
                    totalSales: 0,
                    adSales: 0,
                    adCost: 0,
                    adRevenue: 0,
                    adCvrSum: 0,
                    adCvrCount: 0,
                    latestStock: 0,
                    latestDate: '',
                    adStatus: item.ad_status || '광고안함'
                };
            }
            // 광고 상태 업데이트 (하나라도 광고중이면 광고중으로)
            if (item.ad_status === '광고중') {
                productMap[normName].adStatus = '광고중';
            }
        });
    });

    // 2) 총 판매량 계산 (전날재고 + 입고 - 오늘재고)
    Object.keys(productMap).forEach(productName => {
        let prevStock = null;

        calcDates.forEach(date => {
            const dayData = stockHistory[date];
            if (!dayData) return;

            // 정규화된 이름으로 매칭
            const item = dayData.find(d => normalizeProductName(d.product_name) === productName);
            if (!item) return;

            const stock = item.stock;

            // rangeDates에 포함된 날짜만 판매량 계산 (전날 데이터는 prevStock 설정용)
            if (prevStock !== null && date >= startDate) {
                const receiving = getMappedReceiving(item.product_name, date);
                const sales = prevStock + receiving - stock;
                if (sales > 0) {
                    productMap[productName].totalSales += sales;
                }
            }

            prevStock = stock;

            // 최신 재고량 갱신 (범위 내 날짜만)
            if (date >= startDate && date >= productMap[productName].latestDate) {
                productMap[productName].latestStock = stock;
                productMap[productName].latestDate = date;
            }
        });
    });

    // 3) 광고 판매량, 광고비, 광고매출, 전환율 집계 (adHistory에서)
    Object.keys(adHistory).forEach(date => {
        if (date < startDate || date > endDate) return;
        const dayAd = adHistory[date];
        if (!dayAd || !dayAd.products) return;

        dayAd.products.forEach(prod => {
            let name = prod.product_name;
            if (!name) return;

            // 매핑된 이름이 있으면 그 이름으로 집계
            if (productMapping[name]) {
                name = productMapping[name];
            }
            name = normalizeProductName(name);

            // 기존 재고 상품과 매칭 시도 (부분 문자열 포함)
            const matchedKey = findMatchingProductKey(name, productMap);
            if (matchedKey) {
                name = matchedKey;
            }

            if (!productMap[name]) {
                productMap[name] = {
                    totalSales: 0,
                    adSales: 0,
                    adCost: 0,
                    adRevenue: 0,
                    adCvrSum: 0,
                    adCvrCount: 0,
                    latestStock: 0,
                    latestDate: '',
                    adStatus: '광고중'
                };
            }

            productMap[name].adSales += (prod.ad_sales || 0);
            productMap[name].adCost += Math.floor((prod.ad_cost || 0) * 1.1); // 부가세 10% 포함
            productMap[name].adRevenue += (prod.ad_revenue || 0);
            // 전환율은 평균 계산을 위해 합산
            if (prod.cvr) {
                productMap[name].adCvrSum += parseFloat(prod.cvr) || 0;
                productMap[name].adCvrCount++;
            }
        });
    });

    // 4) 정렬: 어떤 데이터든 있으면 상단, 그 안에서 총 판매량 내림차순
    const sortedProducts = Object.entries(productMap).sort((a, b) => {
        const aHasData = a[1].totalSales > 0 || a[1].adSales > 0 || a[1].adCost > 0 || a[1].latestStock > 0;
        const bHasData = b[1].totalSales > 0 || b[1].adSales > 0 || b[1].adCost > 0 || b[1].latestStock > 0;
        if (aHasData && !bHasData) return -1;
        if (!aHasData && bHasData) return 1;
        if (b[1].totalSales !== a[1].totalSales) return b[1].totalSales - a[1].totalSales;
        return b[1].adSales - a[1].adSales;
    });

    // 5) 테이블 렌더링
    if (sortedProducts.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="8" style="text-align:center; padding:40px; color:var(--text-muted);">해당 기간의 데이터가 없습니다.</td></tr>';
        updateDashStats(0, 0, 0, 0);
        return;
    }

    let html = '';
    let grandTotalSales = 0;
    let grandAdSales = 0;
    let grandOrganicSales = 0;
    let grandAdCost = 0;
    let grandAdRevenue = 0;

    sortedProducts.forEach(([name, data]) => {
        // 자연 판매량 = 총 판매량 - 광고 판매량
        const organicSales = Math.max(0, data.totalSales - data.adSales);
        const hasSales = data.totalSales > 0;

        // ROAS = 광고매출 / 광고비 * 100
        const roas = data.adCost > 0 ? Math.round(data.adRevenue / data.adCost * 100) : 0;
        // 전환율 = 평균 CVR
        const cvr = data.adCvrCount > 0 ? (data.adCvrSum / data.adCvrCount).toFixed(1) : 0;

        grandTotalSales += data.totalSales;
        grandAdSales += data.adSales;
        grandOrganicSales += organicSales;
        grandAdCost += data.adCost;
        grandAdRevenue += data.adRevenue;

        const rowOpacity = hasSales ? '' : ' style="opacity:0.5;"';
        const adBadge = data.adStatus === '광고중'
            ? '<span style="display:inline-block; background:var(--accent-primary); color:#fff; font-size:0.65rem; padding:1px 5px; border-radius:4px; margin-right:4px; vertical-align:middle;">광고</span>'
            : '';

        html += `<tr${rowOpacity}>
            <td style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${escapeHtml(name)}">${adBadge}${escapeHtml(name)}</td>
            <td style="text-align:right; font-weight:bold; color:var(--accent-primary);">${data.totalSales.toLocaleString()}</td>
            <td style="text-align:right;">${data.adSales > 0 ? data.adSales.toLocaleString() : '-'}</td>
            <td style="text-align:right; color:#10b981;">${organicSales > 0 ? organicSales.toLocaleString() : '-'}</td>
            <td style="text-align:right;">${data.latestStock.toLocaleString()}</td>
            <td style="text-align:right; color:var(--danger);">${data.adCost > 0 ? data.adCost.toLocaleString() + '원' : '-'}</td>
            <td style="text-align:right;">${roas > 0 ? roas + '%' : '-'}</td>
            <td style="text-align:right;">${cvr > 0 ? cvr + '%' : '-'}</td>
        </tr>`;
    });

    // 합계 행
    const grandRoas = grandAdCost > 0 ? Math.round(grandAdRevenue / grandAdCost * 100) : 0;

    html += `<tr style="font-weight:bold; border-top:2px solid var(--border-color); background:rgba(99,102,241,0.05);">
        <td>합계</td>
        <td style="text-align:right; color:var(--accent-primary);">${grandTotalSales.toLocaleString()}</td>
        <td style="text-align:right;">${grandAdSales.toLocaleString()}</td>
        <td style="text-align:right; color:#10b981;">${grandOrganicSales.toLocaleString()}</td>
        <td style="text-align:right;">-</td>
        <td style="text-align:right; color:var(--danger);">${grandAdCost.toLocaleString()}원</td>
        <td style="text-align:right;">${grandRoas > 0 ? grandRoas + '%' : '-'}</td>
        <td style="text-align:right;">-</td>
    </tr>`;

    tableBody.innerHTML = html;
    updateDashStats(grandTotalSales, grandAdSales, grandOrganicSales, grandAdCost);
}

// 대시보드 요약 카드 업데이트
function updateDashStats(totalSales, adSales, organicSales, adCost) {
    const el = (id) => document.getElementById(id);
    if (el('dashTotalSales')) el('dashTotalSales').textContent = totalSales.toLocaleString();
    if (el('dashAdSales')) el('dashAdSales').textContent = adSales.toLocaleString();
    if (el('dashOrganicSales')) el('dashOrganicSales').textContent = organicSales.toLocaleString();
    if (el('dashTotalAdCost')) el('dashTotalAdCost').textContent = adCost.toLocaleString() + '원';
}

// ========================================
// 정산내역 탭 기능
// ========================================
let deductionData = [];  // 정산내역 데이터 배열
let deductionHeaders = [];  // 테이블 헤더

// 정산내역 관련 DOM 요소 (동적 바인딩)
const deductionElements = {
    get deductionTab() { return document.getElementById('deductionTab'); },
    get deductionTableHead() { return document.getElementById('deductionTableHead'); },
    get deductionTableBody() { return document.getElementById('deductionTableBody'); },
    get deductionCount() { return document.getElementById('deductionCount'); },
    get deductionLastUpdate() { return document.getElementById('deductionLastUpdate'); }
};

// 정산내역 데이터 로드
function loadDeductionData() {
    try {
        const saved = localStorage.getItem(DEDUCTION_STORAGE_KEY);
        if (saved) {
            const parsed = JSON.parse(saved);
            deductionData = parsed.data || [];
            deductionHeaders = parsed.headers || [];
            // 헤더가 없으면 데이터에서 자동 추출
            if (deductionHeaders.length === 0 && deductionData.length > 0) {
                deductionHeaders = Object.keys(deductionData[0]).filter(k => !k.startsWith('_'));
            }
        }
    } catch (e) {
        console.error('정산내역 데이터 로드 실패:', e);
        deductionData = [];
        deductionHeaders = [];
    }
}

// 정산내역 데이터 저장
function saveDeductionData() {
    try {
        // 현재 월을 마지막 조회 월로 저장
        const now = new Date();
        const lastQueryMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;

        localStorage.setItem(DEDUCTION_STORAGE_KEY, JSON.stringify({
            data: deductionData,
            headers: deductionHeaders,
            lastUpdate: new Date().toISOString(),
            lastQueryMonth: lastQueryMonth
        }));
    } catch (e) {
        console.error('정산내역 데이터 저장 실패:', e);
    }
}


// 정산내역 테이블 렌더링 (월별 필터링 적용)
function renderDeductionTable() {
    if (!deductionElements.deductionTableHead || !deductionElements.deductionTableBody) return;

    // 선택된 연도/월 가져오기
    const yearFilter = document.getElementById('deductionYearFilter');
    const monthFilter = document.getElementById('deductionMonthFilter');
    const selectedYear = yearFilter ? yearFilter.value : null;
    const selectedMonth = monthFilter ? monthFilter.value : null;

    // 빈 행 제거 (증빙일, 정산일, 계산서 번호 모두 비어있으면 제외)
    const validData = deductionData.filter(row => {
        return (row['증빙일'] || row['매출발생일'] || row['정산일'] || row['계산서 번호'] || '').trim() !== '';
    });

    // 필터링된 데이터 (증빙일 기준)
    let filteredData = validData;
    if (selectedYear && selectedMonth) {
        const filterKey = `${selectedYear}-${String(selectedMonth).padStart(2, '0')}`;
        filteredData = validData.filter(row => {
            // 증빙일 컬럼을 우선 사용
            const dateCol = row['증빙일'] || row['매출발생일'] || row['정산일'] || '';
            return dateCol.startsWith(filterKey);
        });
    }

    // 증빙일 기준 정렬 (오래된 순 → 최신순)
    filteredData = [...filteredData].sort((a, b) => {
        const dateA = a['증빙일'] || a['매출발생일'] || a['정산일'] || '';
        const dateB = b['증빙일'] || b['매출발생일'] || b['정산일'] || '';
        return dateA.localeCompare(dateB);
    });

    // 헤더 렌더링
    if (deductionHeaders.length > 0) {
        let headerHtml = '<tr>';
        deductionHeaders.forEach(header => {
            headerHtml += `<th>${escapeHtml(header)}</th>`;
        });
        headerHtml += '</tr>';
        deductionElements.deductionTableHead.innerHTML = headerHtml;
    } else {
        deductionElements.deductionTableHead.innerHTML = '<tr><th>데이터를 조회해주세요</th></tr>';
    }

    // 데이터 렌더링
    if (filteredData.length === 0) {
        const monthText = selectedYear && selectedMonth ? `${selectedYear}년 ${selectedMonth}월` : '';
        deductionElements.deductionTableBody.innerHTML = `
            <tr>
                <td colspan="${deductionHeaders.length || 1}" style="text-align: center; color: var(--text-muted); padding: 40px;">
                    ${monthText} 정산내역 데이터가 없습니다.
                </td>
            </tr>
        `;
        updateDeductionStats(0);
        return;
    }

    // 금액 컬럼별 합계 계산
    const amountTotals = {};
    deductionHeaders.forEach(header => {
        if (header.includes('금액') || header.includes('잔액') || header.includes('지급액')) {
            amountTotals[header] = 0;
        }
    });

    let bodyHtml = '';
    filteredData.forEach(row => {
        bodyHtml += '<tr>';
        deductionHeaders.forEach(header => {
            const value = row[header] || '-';
            // 금액 관련 컬럼은 색상 적용 및 합계 계산
            const isAmount = header.includes('금액') || header.includes('잔액') || header.includes('지급액');
            let cellClass = '';
            if (isAmount && value !== '-') {
                const numValue = parseInt(value.replace(/[^0-9-]/g, '')) || 0;
                if (numValue > 0) cellClass = 'amount-positive';
                else if (numValue < 0) cellClass = 'amount-negative';
                // 합계에 추가
                if (amountTotals.hasOwnProperty(header)) {
                    amountTotals[header] += numValue;
                }
            }
            bodyHtml += `<td class="${cellClass}">${escapeHtml(value)}</td>`;
        });
        bodyHtml += '</tr>';
    });

    // 합계 행 추가
    bodyHtml += '<tr style="background: var(--bg-tertiary); font-weight: bold; border-top: 2px solid var(--primary);">';
    deductionHeaders.forEach((header, index) => {
        if (index === 0) {
            bodyHtml += `<td style="text-align: center;">📊 합계</td>`;
        } else if (amountTotals.hasOwnProperty(header)) {
            const total = amountTotals[header];
            const cellClass = total > 0 ? 'amount-positive' : total < 0 ? 'amount-negative' : '';
            const formattedTotal = total.toLocaleString() + '원';
            bodyHtml += `<td class="${cellClass}">${formattedTotal}</td>`;
        } else {
            bodyHtml += '<td>-</td>';
        }
    });
    bodyHtml += '</tr>';

    deductionElements.deductionTableBody.innerHTML = bodyHtml;
    updateDeductionStats(filteredData.length);
}

// 정산내역 통계 업데이트
function updateDeductionStats(count = null) {
    if (deductionElements.deductionCount) {
        const displayCount = count !== null ? count : deductionData.length;
        deductionElements.deductionCount.textContent = `${displayCount}건`;
    }
    if (deductionElements.deductionLastUpdate) {
        const saved = localStorage.getItem(DEDUCTION_STORAGE_KEY);
        if (saved) {
            const parsed = JSON.parse(saved);
            if (parsed.lastUpdate) {
                const date = new Date(parsed.lastUpdate);
                deductionElements.deductionLastUpdate.textContent =
                    `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
            }
        }
    }
}

// 드롭다운 변경 이벤트 리스너
document.addEventListener('change', (e) => {
    if (e.target.id === 'deductionYearFilter' || e.target.id === 'deductionMonthFilter') {
        updateDeductionPeriodLabel();
        renderDeductionTable();
    }
});

// 정산내역 기간 라벨 업데이트
function updateDeductionPeriodLabel() {
    const yearFilter = document.getElementById('deductionYearFilter');
    const monthFilter = document.getElementById('deductionMonthFilter');
    const label = document.getElementById('deductionPeriodLabel');
    if (yearFilter && monthFilter && label) {
        label.textContent = `${yearFilter.value}년 ${monthFilter.value}월`;
    }
}

// 정산내역 ◀▶ 월 이동 버튼
document.addEventListener('click', (e) => {
    const yearFilter = document.getElementById('deductionYearFilter');
    const monthFilter = document.getElementById('deductionMonthFilter');
    if (!yearFilter || !monthFilter) return;

    if (e.target.id === 'prevDeductionMonthBtn' || e.target.closest('#prevDeductionMonthBtn')) {
        let y = parseInt(yearFilter.value);
        let m = parseInt(monthFilter.value);
        m--;
        if (m < 1) { m = 12; y--; }
        yearFilter.value = y;
        monthFilter.value = m;
        updateDeductionPeriodLabel();
        renderDeductionTable();
    } else if (e.target.id === 'nextDeductionMonthBtn' || e.target.closest('#nextDeductionMonthBtn')) {
        let y = parseInt(yearFilter.value);
        let m = parseInt(monthFilter.value);
        m++;
        if (m > 12) { m = 1; y++; }
        yearFilter.value = y;
        monthFilter.value = m;
        updateDeductionPeriodLabel();
        renderDeductionTable();
    }
});

// 데이터 고유 키 생성 (중복 체크용, _query_month 제외)
function getRowKey(row) {
    const keys = Object.keys(row).filter(k => !k.startsWith('_')).sort();
    return keys.map(k => row[k]).join('|');
}

// ── 공통 정산내역 수집 함수 (5일 버퍼 로직 포함) ──
async function fetchDeductionDataWithBuffer(userId, userPw) {
    let startYear = 2025;
    let startMonth = 11;

    if (deductionData.length > 0) {
        try {
            const bufferDate = new Date();
            bufferDate.setDate(bufferDate.getDate() - 4);
            startYear = bufferDate.getFullYear();
            startMonth = bufferDate.getMonth() + 1;
        } catch (e) {
            console.error("정산 조회 계산 오류:", e);
        }
    }

    try {
        const response = await fetch(`${API_BASE_URL}/api/fetch-deduction`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: userId,
                user_pw: userPw,
                start_year: startYear,
                start_month: startMonth
            })
        });

        if (response.ok) {
            const result = await response.json();
            if (result.success && result.data) {
                // 월별 병합: 새로 수집한 월의 데이터는 전체 교체, 나머지 월 보존
                const newMonths = new Set(result.data.map(r => r._query_month).filter(Boolean));
                const kept = deductionData.filter(r => !newMonths.has(r._query_month || ''));
                const newCount = result.data.length;

                deductionData = [...kept, ...result.data];

                if (result.data.length > 0) {
                    deductionHeaders = Object.keys(result.data[0]).filter(k => !k.startsWith('_'));
                }

                deductionHistory = deductionData;
                saveDeductionData();
                renderDeductionTable();
                if (typeof renderRocketTab === 'function') renderRocketTab();

                return { success: true, count: newCount, total: deductionData.length };
            }
            return { success: false, error: result.error };
        }
    } catch (e) {
        console.error("fetchDeductionDataWithBuffer 에러:", e);
    }
    return { success: false };
}

// 재고 수집 버튼 (재고 + 입고만)
document.addEventListener('click', async (e) => {
    if (e.target.id === 'fetchStockBtn' || e.target.closest('#fetchStockBtn')) {
        const { userId, userPw } = getCredentials();

        if (!userId || !userPw) {
            showToast('먼저 로그인해주세요.', 'error');
            showLogin();
            return;
        }

        await fetchStockAndReceiving(userId, userPw);
    }
});

// 전체 데이터 수집 버튼 (재고 + 입고 + 정산내역)
document.addEventListener('click', async (e) => {
    if (e.target.id === 'fetchAllDataBtn' || e.target.closest('#fetchAllDataBtn')) {
        const { userId, userPw } = getCredentials();

        if (!userId || !userPw) {
            showToast('먼저 로그인해주세요.', 'error');
            showLogin();
            return;
        }

        await fetchAllData(userId, userPw);
    }
});

// 정산내역 조회 버튼
document.addEventListener('click', async (e) => {
    if (e.target.id === 'fetchDeductionBtn' || e.target.closest('#fetchDeductionBtn')) {
        const { userId, userPw } = getCredentials();

        if (!userId || !userPw) {
            showToast('먼저 재고 탭에서 로그인해주세요.', 'error');
            return;
        }

        showToast('정산내역 데이터 조회 중... (월별 병합 방식)', 'info');

        try {
            const result = await fetchDeductionDataWithBuffer(userId, userPw);
            if (result.success) {
                if (result.count > 0) {
                    showToast(`정산 데이터 ${result.count}건 갱신 완료! (총 ${result.total}건)`, 'success');
                } else {
                    showToast('새로운 데이터가 없습니다.', 'info');
                }
            } else {
                showToast('정산내역 조회 실패', 'error');
            }
        } catch (error) {
            console.error('정산내역 조회 에러:', error);
            showToast('정산 내역 조회 중 오류 발생', 'error');
        }
    }
});

// 정산내역 초기화 버튼
document.addEventListener('click', (e) => {
    if (e.target.id === 'clearDeductionBtn' || e.target.closest('#clearDeductionBtn')) {
        if (confirm('정산내역 데이터를 모두 삭제하시겠습니까?')) {
            deductionData = [];
            deductionHistory = [];
            deductionHeaders = [];
            localStorage.removeItem(DEDUCTION_STORAGE_KEY);
            renderDeductionTable();
            showToast('정산내역 데이터가 초기화되었습니다.', 'success');
        }
    }
});

// 정산내역 데이터 초기 로드
loadDeductionData();
console.log('📋 정산내역 기능 로드 완료');

// ========================================
// 광고비 탭 기능
// ========================================

// ========================================

let currentAdMonthDate = new Date(); // 기본값: 이번 달
currentAdMonthDate.setDate(1); // 1일로 설정하여 월 기준 처리

const adElements = {
    get monthInput() { return document.getElementById('adMonthInput'); },
    get prevBtn() { return document.getElementById('prevAdMonthBtn'); },
    get nextBtn() { return document.getElementById('nextAdMonthBtn'); },
    get tableBody() { return document.getElementById('adTableBody'); },
    get tableFoot() { return document.getElementById('adTableFoot'); }
};

function formatMonth(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    return `${year}-${month}`;
}

function renderAdTab() {
    if (!adElements.monthInput) return;

    // 월 입력창 설정
    const monthStr = formatMonth(currentAdMonthDate);
    adElements.monthInput.value = monthStr;

    // 기간 라벨 업데이트
    const adPeriodLabel = document.getElementById('adPeriodLabel');
    if (adPeriodLabel) {
        adPeriodLabel.textContent = `${currentAdMonthDate.getFullYear()}년 ${currentAdMonthDate.getMonth() + 1}월`;
    }

    updateAdTable();
}

function updateAdTable() {
    const tableBody = adElements.tableBody;
    const tableFoot = adElements.tableFoot;
    if (!tableBody || !tableFoot) return;

    tableBody.innerHTML = '';
    tableFoot.innerHTML = '';

    const targetYear = currentAdMonthDate.getFullYear();
    const targetMonth = currentAdMonthDate.getMonth() + 1;

    // 해당 월의 데이터 필터링
    const monthlyData = [];
    Object.keys(adHistory).forEach(dateStr => {
        const [y, m, d] = dateStr.split('-').map(Number);
        if (y === targetYear && m === targetMonth) {
            monthlyData.push({
                date: dateStr,
                ...adHistory[dateStr]
            });
        }
    });

    // 날짜 내림차순 정렬 (최신 날짜가 위로)
    monthlyData.sort((a, b) => new Date(b.date) - new Date(a.date));

    if (monthlyData.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 2rem;">데이터가 없습니다.</td></tr>';
        return;
    }

    // 합계 계산 변수
    let totalAdCost = 0;
    let totalAdSales = 0;
    let totalSales = 0;
    let totalRoasSum = 0; // 평균 계산용 (데이터 있는 행만)
    let totalCvrSum = 0;  // 평균 계산용 (데이터 있는 행만)
    let validRows = 0;

    monthlyData.forEach((item, idx) => {
        const row = document.createElement('tr');
        row.style.cursor = 'pointer';
        row.style.transition = 'background 0.2s';

        const adCost = item.ad_cost || 0;
        const adSales = item.ad_sales || 0;
        const sales = item.total_sales || 0;
        const roas = item.roas || 0;
        const cvr = item.conversion_rate || 0;

        totalAdCost += adCost;
        totalAdSales += adSales;
        totalSales += sales;
        totalRoasSum += roas;
        totalCvrSum += cvr;
        validRows++;

        const hasProducts = item.products && item.products.length > 0;
        const arrowSpan = hasProducts ? '<span class="ad-row-arrow" style="margin-right:6px; display:inline-block; transition:transform 0.2s;">▶</span>' : '';

        row.innerHTML = `
            <td>${arrowSpan}${item.date}</td>
            <td class="td-stock">${adCost.toLocaleString()}원</td>
            <td class="td-stock">${adSales.toLocaleString()}개</td>
            <td class="td-stock">${sales.toLocaleString()}개</td>
            <td class="td-stock">${roas}%</td>
            <td class="td-stock">${cvr}%</td>
        `;
        tableBody.appendChild(row);

        // 상품별 상세 내역 추가 (기본 숨김, 클릭하면 펼쳐짐)
        if (hasProducts) {
            const detailRow = document.createElement('tr');
            detailRow.style.backgroundColor = 'rgba(99, 102, 241, 0.05)';
            detailRow.style.display = 'none'; // 기본 숨김
            detailRow.classList.add('ad-detail-row');

            const detailCell = document.createElement('td');
            detailCell.colSpan = 6;
            detailCell.style.padding = '0';

            let detailHtml = `
                <div style="padding: 10px 20px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                        <span style="font-weight:600; color:var(--text-secondary); font-size:0.85rem;">📦 상품별 상세 내역</span>
                    </div>
                    <table style="width: 100%; border-collapse: collapse; font-size: 0.85rem;">
                        <thead>
                            <tr style="border-bottom: 1px solid var(--border-color); color: var(--text-secondary);">
                                <th style="text-align: left; padding: 5px;">상품명</th>
                                <th style="text-align: right; padding: 5px;">클릭률</th>
                                <th style="text-align: right; padding: 5px;">광고 전환 판매수</th>
                                <th style="text-align: right; padding: 5px;">광고 전환 매출</th>
                                <th style="text-align: right; padding: 5px;">전환율</th>
                                <th style="text-align: right; padding: 5px;">집행 광고비(+10%)</th>
                                <th style="text-align: right; padding: 5px;">광고수익률</th>
                            </tr>
                        </thead>
                        <tbody>
            `;

            item.products.forEach(prod => {
                const isZeroSales = (prod.ad_sales || 0) === 0;
                const adCostWithVat = Math.floor((prod.ad_cost || 0) * 1.1);

                detailHtml += `
                    <tr style="border-bottom: 1px dashed var(--border-color); ${isZeroSales ? 'opacity:0.6;' : ''}">
                        <td style="padding: 5px; color: var(--text-primary); font-weight: 500; max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${prod.product_name || '-'}">${prod.product_name || '-'}</td>
                        <td style="text-align: right; padding: 5px;">${prod.ctr || 0}%</td>
                        <td style="text-align: right; padding: 5px; color: var(--accent-primary); font-weight: bold;">${(prod.ad_sales || 0).toLocaleString()}</td>
                        <td style="text-align: right; padding: 5px;">${(prod.ad_revenue || 0).toLocaleString()}원</td>
                        <td style="text-align: right; padding: 5px;">${prod.cvr || 0}%</td>
                        <td style="text-align: right; padding: 5px;">${adCostWithVat.toLocaleString()}원</td>
                        <td style="text-align: right; padding: 5px;">${prod.roas || 0}%</td>
                    </tr>
                `;
            });

            detailHtml += `
                        </tbody>
                    </table>
                </div>
            `;

            detailCell.innerHTML = detailHtml;
            detailRow.appendChild(detailCell);
            tableBody.appendChild(detailRow);

            // 날짜 행 클릭 시 상세 내역 토글
            row.addEventListener('click', () => {
                const isVisible = detailRow.style.display !== 'none';
                detailRow.style.display = isVisible ? 'none' : 'table-row';
                const arrow = row.querySelector('.ad-row-arrow');
                if (arrow) {
                    arrow.style.transform = isVisible ? 'rotate(0deg)' : 'rotate(90deg)';
                }
            });

            // 마우스 호버 효과
            row.addEventListener('mouseenter', () => { row.style.background = 'rgba(99, 102, 241, 0.1)'; });
            row.addEventListener('mouseleave', () => { row.style.background = ''; });
        }
    });

    // 합계 행 추가
    const avgRoas = validRows > 0 ? (totalRoasSum / validRows).toFixed(0) : 0;
    const avgCvr = validRows > 0 ? (totalCvrSum / validRows).toFixed(0) : 0;

    const footRow = document.createElement('tr');
    footRow.innerHTML = `
        <td style="font-weight: bold;">월 합계/평균</td>
        <td class="td-stock" style="color: var(--accent-primary);">${totalAdCost.toLocaleString()}원</td>
        <td class="td-stock">${totalAdSales.toLocaleString()}개</td>
        <td class="td-stock">${totalSales.toLocaleString()}개</td>
        <td class="td-stock">${avgRoas}%</td>
        <td class="td-stock">${avgCvr}%</td>
    `;
    tableFoot.appendChild(footRow);
}

// 이벤트 리스너 설정
document.addEventListener('DOMContentLoaded', () => {
    // 정산내역 필터 초기화 (2개월 전)
    const deductionYearFilter = document.getElementById('deductionYearFilter');
    const deductionMonthFilter = document.getElementById('deductionMonthFilter');
    if (deductionYearFilter && deductionMonthFilter) {
        deductionYearFilter.value = marginYear;
        deductionMonthFilter.value = marginMonth;
    }
    updateDeductionPeriodLabel();

    // 날짜(월) 변경
    if (adElements.monthInput) {
        adElements.monthInput.addEventListener('change', (e) => {
            if (e.target.value) {
                const [y, m] = e.target.value.split('-');
                currentAdMonthDate = new Date(y, m - 1, 1);
                renderAdTab();
            }
        });
    }

    // 이전/다음 달
    if (adElements.prevBtn) {
        adElements.prevBtn.addEventListener('click', () => {
            currentAdMonthDate.setMonth(currentAdMonthDate.getMonth() - 1);
            renderAdTab();
        });
    }

    if (adElements.nextBtn) {
        adElements.nextBtn.addEventListener('click', () => {
            currentAdMonthDate.setMonth(currentAdMonthDate.getMonth() + 1);
            renderAdTab();
        });
    }

    // 달력 아이콘 클릭 (월 선택)
    const dateWrapper = document.querySelector('#adTab .date-picker-wrapper');
    if (dateWrapper && adElements.monthInput) {
        dateWrapper.addEventListener('click', () => {
            adElements.monthInput.showPicker();
        });
    }

    // 초기 렌더링 (만약 현재 탭이 광고탭이면)
    if (document.querySelector('.tab-content.active')?.id === 'adTab') {
        renderAdTab();
    }
    // 광고비 수집 버튼
    const fetchAdBtn = document.getElementById('fetchAdBtn');
    if (fetchAdBtn) {
        fetchAdBtn.addEventListener('click', async () => {
            const { userId, userPw } = getCredentials();

            if (!userId || !userPw) {
                showToast('로그인이 필요합니다.', 'error');
                return;
            }

            if (confirm('광고비 데이터를 수집하시겠습니까? (약 1분 소요)')) {
                await fetchAdDataOnly(userId, userPw);
            }
        });
    }
});

// 광고비 데이터만 독립적으로 수집
async function fetchAdDataOnly(userId, userPw) {
    showLoading('광고 데이터를 불러오는 중...');
    elements.loadingStatus.textContent = '📢 광고 리포트 수집 요청 중...';

    try {
        const response = await fetch(`${API_BASE_URL}/api/fetch-ad-report`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId, user_pw: userPw, days_back: 7 })
        });

        if (response.ok) {
            const result = await response.json();
            if (result.success) {
                if (result.background) {
                    // 백그라운드 수집 → 완료까지 폴링
                    showToast('📊 광고비 수집이 시작되었습니다. 3~5분 후 자동으로 불러옵니다.', 'info');
                    elements.loadingStatus.textContent = '📊 백그라운드 수집 중... (3~5분 소요)';

                    // 30초마다 캐시 확인 (최대 6분)
                    let attempts = 0;
                    const pollInterval = setInterval(async () => {
                        attempts++;
                        try {
                            const cacheRes = await fetch(`${API_BASE_URL}/api/cached-ad`);
                            const cacheData = await cacheRes.json();
                            if (cacheData.success && cacheData.data) {
                                const today = new Date().toISOString().split('T')[0];
                                const yesterday = new Date(Date.now() - 86400000).toISOString().split('T')[0];
                                // 어제 데이터가 새로 들어왔는지 확인
                                if (cacheData.data[yesterday] || cacheData.data[today]) {
                                    clearInterval(pollInterval);
                                    Object.entries(cacheData.data).forEach(([dateStr, dayData]) => {
                                        adHistory[dateStr] = dayData;
                                    });
                                    saveHistory();
                                    const adYesterday = new Date();
                                    adYesterday.setDate(adYesterday.getDate() - 1);
                                    currentAdDate = adYesterday;
                                    renderAdTab();
                                    showResult();
                                    renderPivotTable();
                                    updateStats();
                                    showToast(`✅ 광고비 데이터 수집 완료!`, 'success');
                                    return;
                                }
                            }
                        } catch (e) { /* 폴링 실패 무시 */ }

                        if (attempts >= 12) { // 6분 초과
                            clearInterval(pollInterval);
                            showResult();
                            showToast('⏰ 광고비 수집 시간 초과. "새로 조회"로 확인해주세요.', 'warning');
                        } else {
                            elements.loadingStatus.textContent = `📊 백그라운드 수집 중... (${attempts * 30}초 경과)`;
                        }
                    }, 30000);
                } else if (result.data_by_date) {
                    for (const [dateStr, dayData] of Object.entries(result.data_by_date)) {
                        const existing = adHistory[dateStr];
                        if (existing && existing.products && existing.products.length > 0 && (!dayData.products || dayData.products.length === 0)) {
                            dayData.products = existing.products;
                        }
                        adHistory[dateStr] = dayData;
                    }
                    saveHistory();
                    const yesterday = new Date();
                    yesterday.setDate(yesterday.getDate() - 1);
                    currentAdDate = yesterday;
                    renderAdTab();
                    showToast(`✅ 광고비 데이터 수집 완료!`, 'success');
                    showResult();
                    renderPivotTable();
                    updateStats();
                }
            } else {
                showError(result.error || '광고 데이터 수집 실패');
                showResult();
            }
        } else {
            showError('서버 연결 실패');
            showResult();
        }
    } catch (e) {
        console.error('광고 수집 오류:', e);
        showError('광고 수집 중 오류가 발생했습니다.');
        showResult();
    }
}

// 초기화 및 자동 로그인 처리
document.addEventListener('DOMContentLoaded', () => {
    // 저장된 아이디/비번 불러오기
    const savedId = localStorage.getItem('coupang_user_id');
    const savedPw = localStorage.getItem('coupang_user_pw');

    if (savedId && savedPw) {
        if (elements.userIdInput) elements.userIdInput.value = savedId;
        if (elements.userPwInput) elements.userPwInput.value = savedPw;
    }

    // 기존 데이터가 있으면 자동으로 대시보드 표시
    if (Object.keys(stockHistory).length > 0) {
        showResult();
        renderDashboard();
    }

    // 서버에서 캐시 데이터 로드 (Vercel/원격 환경에서도 데이터 표시)
    loadAllCachedData().then(loaded => {
        if (loaded > 0) {
            // 데이터가 새로 로드되었으면 화면 갱신
            if (Object.keys(stockHistory).length > 0) {
                showResult();
                renderDashboard();
                if (typeof renderPivotTable === 'function') renderPivotTable();
                if (typeof updateStats === 'function') updateStats();
            }
            // 정산내역 탭도 갱신
            if (typeof renderDeductionTable === 'function') renderDeductionTable();
            showToast(`서버에서 데이터 ${loaded}종 로드 완료`, 'success');
        }
    }).catch(e => console.log('서버 캐시 로드 실패 (오프라인 모드):', e));

    // 비밀번호 입력창에서 엔터키 입력 시 로그인 실행
    if (elements.userPwInput) {
        elements.userPwInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const loginBtn = document.querySelector('.login-form button[type="submit"]');
                if (loginBtn) loginBtn.click();
            }
        });
    }
});

// 광고비 상세에서 판매 0인 상품 토글
function toggleAdZeroRows(btn) {
    const detailTable = btn.closest('div').nextElementSibling;
    const zeroRows = detailTable.querySelectorAll('.ad-zero-sales-row');

    if (zeroRows.length === 0) return;

    const isHidden = zeroRows[0].style.display === 'none';

    zeroRows.forEach(row => {
        row.style.display = isHidden ? 'table-row' : 'none';
    });

    btn.textContent = isHidden ? `판매 없는 상품 숨기기 (${zeroRows.length})` : `판매 없는 상품 보기 (${zeroRows.length})`;
    btn.classList.toggle('active', isHidden);
}
