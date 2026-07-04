import os
import smtplib
import json
import urllib.request
from urllib.error import HTTPError
import time
from datetime import datetime, timedelta
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

def fetch_api_data(url: str, retries=3) -> list:
    # 🔥 봇(Bot) 차단 방화벽을 뚫기 위한 크롬 위장 헤더
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'
    }
    
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8")
            
            resp_json = json.loads(raw)
            items_data = resp_json.get("response", {}).get("body", {}).get("items", {})
            
            if not items_data or items_data == "" or isinstance(items_data, str):
                return []
                
            items = items_data.get("item", [])
            if isinstance(items, dict):
                return [items]
            return items
            
        except HTTPError as e:
            err_msg = ""
            try: err_msg = e.read().decode('utf-8', errors='ignore')
            except: pass
            print(f"⚠️ API 통신 에러 (HTTP {e.code}): {err_msg[:200]}")
            time.sleep(2)
        except Exception as e:
            print(f"⚠️ 기타 통신 실패: {e}")
            time.sleep(2)
            
    return None

def get_subscription_data() -> list:
    # 🔥 [수정 완료] 강제 타임머신을 끄고, 한국 시간(KST) '오늘'을 자동으로 계산합니다.
    today = datetime.utcnow() + timedelta(hours=9)
    today = today.replace(hour=0, minute=0, second=0, microsecond=0)
    
    today_str = today.strftime('%Y-%m-%d')
    print(f"📅 데이터 매칭 정밀 필터링 기준일: {today_str}")

    if not PUBLIC_API_KEY:
        return ["⚠️ PUBLIC_DATA_API_KEY가 깃허브에 설정되지 않았습니다."]

    safe_key = PUBLIC_API_KEY.strip()

    # 🔥 [수정 완료] 주소를 다시 청약홈 진짜 데이터가 있는 구형 메인 서버로 원복했습니다.
    url_apt = f"https://apis.data.go.kr/B551011/APTLttotPblancSvc/getAPTLttotPblancMstList?serviceKey={safe_key}&numOfRows=1000&pageNo=1&_type=json"
    url_remndr = f"https://apis.data.go.kr/B551011/APTLttotPblancSvc/getRemndrMstList?serviceKey={safe_key}&numOfRows=1000&pageNo=1&_type=json"

    print("[API] 공공데이터포털 실시간 서버(apis.data.go.kr) 다운로드 가동...")
    apt_items = fetch_api_data(url_apt)
    remndr_items = fetch_api_data(url_remndr)
    
    if apt_items is None and remndr_items is None:
        return ["⚠️ 공공데이터포털 정부 서버 장애 또는 인증 오류로 데이터를 불러올 수 없습니다."]
        
    apt_items = apt_items or []
    remndr_items = remndr_items or []
    unique_results = set()

    for item in apt_items:
        name = item.get("houseNm", "").strip()
        area = item.get("hssplyAdres", "").strip()
        if not any(k in area for k in ["서울", "경기", "인천"]): continue

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
        if tags: unique_results.add(f"[{'/'.join(tags)}] {name} ({area})")

    for item in remndr_items:
        name = item.get("houseNm", "").strip()
        area = item.get("hssplyAdres", "").strip()
        if not any(k in area for k in ["서울", "경기", "인천"]): continue

        tags = []
        przwin_de = parse_to_date(item.get("przwinPblancDe"))
        cntrct_start = parse_to_date(item.get("cntrctCnclsBgnde"))
        cntrct_end = parse_to_date(item.get("cntrctCnclsEndde"))
        sub_start = parse_to_date(item.get("subscrptRceptBgnde"))
        sub_end = parse_to_date(item.get("subscrptRceptEndde"))

        if sub_start and sub_end and sub_start <= today <= sub_end: tags.append("무순위접수")
        if przwin_de and przwin_de == today: tags.append("당첨자발표")
        if cntrct_start and cntrct_end and cntrct_start <= today <= cntrct_end: tags.append("계약일")
        if tags: unique_results.add(f"[{'/'.join(tags)}] {name} ({area})")

    results = sorted(list(unique_results))
    print(f"🎯 [매칭 완료] 오늘 기준 검증 타깃 단지 수: 총 {len(results)}건")
    return results

def send_email(contents: list):
    # 메일 발송용 날짜도 오늘 날짜로 자동 동기화
    today_str = (datetime.utcnow() + timedelta(hours=9)).strftime('%Y-%m-%d')
    no_data_keywords = ["없습니다", "없음", "오류", "실패", "누락", "⚠️"]
    no_data = not contents or any(k in contents[0] for k in no_data_keywords)

    if no_data:
        text = contents[0] if contents else "오늘 진행 중인 수도권 아파트 공급 일정이 없습니다."
        body_html = f"<p style='color:#666;font-size:14px;font-weight:bold;text-align:center;padding:25px 0;'>ℹ️ {text}</p>"
        cnt_str = "0건"
    else:
        items_html = "".join([f"<li style='margin:14px 0;font-size:15px;font-weight:bold;color:#0056b3;border-bottom:1px dashed #eee;padding-bottom:10px;'>🏢 {item}</li>" for item in contents])
        body_html = f"<ul style='padding-left:10px;list-style-type:none;'>{items_html}</ul>"
        cnt_str = f"{len(contents)}건"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔔 [청약홈 동기화] 수도권 정밀 캘린더 ({cnt_str})"
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECEIVER_EMAIL

    html = f"""
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family:'Malgun Gothic',sans-serif;line-height:1.6;color:#333;margin:0;padding:20px;">
      <div style="max-width:700px;margin:0 auto;border:1px solid #e9ecef;border-radius:8px;overflow:hidden;box-shadow:0 4px 10px rgba(0,0,0,0.05);">
        <div style="background-color:#1a73e8;padding:24px;text-align:center;color:#fff;">
          <h2 style="margin:0;font-size:22px;font-weight:bold;letter-spacing:-0.5px;">🔔 수도권 청약 상세 캘린더</h2>
          <p style="margin:8px 0 0 0;font-size:14px;opacity:0.9;">기준일자: {today_str}</p>
        </div>
        <div style="padding:24px;background-color:#fff;">
          {body_html}
        </div>
      </div>
    </body>
    </html>"""
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print("📧 이메일 인코딩 발송 성공!")
    except Exception as e:
        print(f"❌ 이메일 발송 실패: {e}")

if __name__ == "__main__":
    data = get_subscription_data()
    send_email(data)
