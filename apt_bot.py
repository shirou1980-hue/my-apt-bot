import os
import smtplib
import json
import urllib.request
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_SERVER      = "smtp.gmail.com"
SMTP_PORT        = 587
SENDER_EMAIL     = "shirou1980@gmail.com"
SENDER_PASSWORD  = os.environ.get("GMAIL_PASSWORD")
RECEIVER_EMAIL   = os.environ.get("RECEIVER_EMAIL")
PUBLIC_API_KEY   = os.environ.get("PUBLIC_DATA_API_KEY", "")

def parse_to_date(date_str: str):
    if not date_str:
        return None
    clean_str = str(date_str).replace("-", "").strip()
    if len(clean_str) >= 8:
        try:
            return datetime.strptime(clean_str[:8], "%Y%m%d")
        except:
            return None
    return None

def fetch_api_data(url: str) -> list:
    try:
        req = urllib.request.Request(url)
        # 정부 서버 부하를 고려해 타임아웃을 20초로 넉넉히 줍니다.
        with urllib.request.urlopen(req, timeout=20) as resp:
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

def get_subscription_data() -> list:
    # 🔥 [타임머신 테스트] 내일(26일) 날짜 고정. 테스트 성공 후 오늘 날짜로 원복하시면 됩니다.
    today = datetime(2026, 5, 26)
    print(f"📅 데이터 매칭 정밀 필터링 기준일: {today.strftime('%Y-%m-%d')}")

    if not PUBLIC_API_KEY:
        return ["⚠️ PUBLIC_DATA_API_KEY가 설정되지 않았습니다."]

    # 🔥 서버를 터뜨리는 불법 파라미터를 제거하고 순정 1000건만 요청합니다.
    url_apt = f"https://apis.data.go.kr/B551011/APTLttotPblancSvc/getAPTLttotPblancMstList?serviceKey={PUBLIC_API_KEY}&numOfRows=1000&pageNo=1&_type=json"
    url_remndr = f"https://apis.data.go.kr/B551011/APTLttotPblancSvc/getRemndrMstList?serviceKey={PUBLIC_API_KEY}&numOfRows=1000&pageNo=1&_type=json"

    print("[API] 공공데이터포털 안전 규격 데이터 다운로드 가동...")
    apt_items = fetch_api_data(url_apt)
    remndr_items = fetch_api_data(url_remndr)
    
    unique_results = set()

    # 1) 일반 아파트 마스터 데이터 매칭
    for item in apt_items:
        name = item.get("houseNm", "").strip()
        area = item.get("hssplyAdres", "").strip()
        
        # 수도권(서울, 경기, 인천) 스크리닝
        if not any(k in area for k in ["서울", "경기", "인천"]):
            continue

        tags = []
        przwin_de = parse_to_date(item.get("przwinPblancDe"))
        cntrct_start = parse_to_date(item.get("cntrctCnclsBgnde"))
        cntrct_end = parse_to_date(item.get("cntrctCnclsEndde"))
        
        spsply_start = parse_to_date(item.get("spsplyRceptBgnde"))
        spsply_end = parse_to_date(item.get("spsplyRceptEndde"))
        gnrl_start = parse_to_date(item.get("rceptBgnde"))
        gnrl_end = parse_to_date(item.get("rceptEndde"))

        if spsply_start and spsply_end and spsply_start <= today <= spsply_end: tags.append("특공접수")
        if gnrl_start and gnrl_end and gnrl_start <= today <= gnrl_end: tags.append("일반접수")
        if przwin_de and przwin_de == today: tags.append("당첨자발표")
        if cntrct_start and cntrct_end and cntrct_start <= today <= cntrct_end: tags.append("계약일")

        if tags:
            unique_results.add(f"[{'/'.join(tags)}] {name} ({area})")

    # 2) 무순위 / 잔여세대 마스터 데이터 매칭
    for item in remndr_items:
        name = item.get("houseNm", "").strip()
        area = item.get("hssplyAdres", "").strip()
        
        if not any(k in area for k in ["서울", "경기", "인천"]):
            continue

        tags = []
        przwin_de = parse_to_date(item.get("przwinPblancDe"))
        cntrct_start = parse_to_date(item.get("cntrctCnclsBgnde"))
        cntrct_end = parse_to_date(item.get("cntrctCnclsEndde"))
        
        sub_start = parse_to_date(item.get("subscrptRceptBgnde"))
        sub_end = parse_to_date(item.get("subscrptRceptEndde"))
if __name__ == "__main__":
    data = get_subscription_data()
    send_email(data)
