import os
import json
import urllib.request
from datetime import datetime

PUBLIC_API_KEY = os.environ.get("PUBLIC_DATA_API_KEY", "")

def fetch_api_data(url: str) -> list:
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        items_data = data.get("response", {}).get("body", {}).get("items", {})
        
        if not items_data or items_data == "" or isinstance(items_data, str):
            return []
            
        items = items_data.get("item", [])
        if isinstance(items, dict):
            return [items]
        return items
    except Exception as e:
        print(f"⚠️ API 데이터 수신 실패: {e}")
        return []

def run_diagnostic():
    today = datetime(2026, 5, 26)
    curr_m = today.strftime("%Y%m")
    prev_m = f"{today.year-1}12" if today.month == 1 else f"{today.year}{today.month-1:02d}"

    print("==================================================")
    print("🔍 [진단 모드] 공공데이터포털 API 원시 데이터 확인")
    print("==================================================")
    
    if not PUBLIC_API_KEY:
        print("❌ PUBLIC_DATA_API_KEY가 없습니다.")
        return

    # 일반분양 마스터 (당월 + 전월)
    url_apt_curr = f"https://apis.data.go.kr/B551011/APTLttotPblancSvc/getAPTLttotPblancMstList?serviceKey={PUBLIC_API_KEY}&numOfRows=1000&pageNo=1&startmonth={curr_m}&_type=json"
    url_apt_prev = f"https://apis.data.go.kr/B551011/APTLttotPblancSvc/getAPTLttotPblancMstList?serviceKey={PUBLIC_API_KEY}&numOfRows=1000&pageNo=1&startmonth={prev_m}&_type=json"
    
    print(f"\n📥 1. 일반분양 API 요청 중... (조회월: {prev_m}, {curr_m})")
    apt_data = fetch_api_data(url_apt_curr) + fetch_api_data(url_apt_prev)
    print(f"✅ 일반분양 원시 데이터 총 {len(apt_data)}건 수신 완료")

    print("\n[일반분양 데이터 샘플 (최대 100건 확인)]")
    for i, item in enumerate(apt_data[:100]):
        name = item.get("houseNm", "알수없음")
        area = item.get("hssplyAdres", "알수없음")
        spsply_start = item.get("spsplyRceptBgnde", "")
        gnrl_start = item.get("rceptBgnde", "")
        print(f"{i+1}. {name} | 지역: {area} | 특공시작: {spsply_start} | 일반시작: {gnrl_start}")

    print("\n--------------------------------------------------")

    # 무순위 마스터 (당월 + 전월)
    url_remndr_curr = f"https://apis.data.go.kr/B551011/APTLttotPblancSvc/getRemndrMstList?serviceKey={PUBLIC_API_KEY}&numOfRows=1000&pageNo=1&startmonth={curr_m}&_type=json"
    url_remndr_prev = f"https://apis.data.go.kr/B551011/APTLttotPblancSvc/getRemndrMstList?serviceKey={PUBLIC_API_KEY}&numOfRows=1000&pageNo=1&startmonth={prev_m}&_type=json"
    
    print(f"\n📥 2. 무순위 API 요청 중... (조회월: {prev_m}, {curr_m})")
    remndr_data = fetch_api_data(url_remndr_curr) + fetch_api_data(url_remndr_prev)
    print(f"✅ 무순위 원시 데이터 총 {len(remndr_data)}건 수신 완료")

    print("\n[무순위 데이터 샘플 (최대 100건 확인)]")
    for i, item in enumerate(remndr_data[:100]):
        name = item.get("houseNm", "알수없음")
        area = item.get("hssplyAdres", "알수없음")
        sub_start = item.get("subscrptRceptBgnde", "")
        print(f"{i+1}. {name} | 지역: {area} | 무순위시작: {sub_start}")
        
    print("\n==================================================")
    print("진단 스크립트 실행 완료. GitHub Actions 로그 창을 확인해 주세요.")
    print("==================================================")

if __name__ == "__main__":
    run_diagnostic()
