import os
import smtplib
import json
import urllib.request
import urllib.parse
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
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json'
    }
    
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8")
            
            resp_json = json.loads(raw)
            if "data" in resp_json:
                return resp_json["data"]
            return []
            
        except HTTPError as e:
            try: err_msg = e.read().decode('utf-8', errors='ignore')
            except: err_msg = ""
            print(f"⚠️ API 통신 에러 (HTTP {e.code}): {err_msg[:200]}")
            time.sleep(2)
        except Exception as e:
            print(f"⚠️ 기타 통신 실패: {e}")
            time.sleep(2)
            
    return None

def get_subscription_data() -> tuple:
    # 🌟 오늘, 그리고 1주 전 ~ 2주 후의 날짜 윈도우 계산
    today = datetime.utcnow() + timedelta(hours=9)
    today = today.replace(hour=0, minute=0, second=0, microsecond=0)
    
    start_window = today - timedelta(days=7)
    end_window = today + timedelta(days=14)
    
    window_str = f"{start_window.strftime('%Y-%m-%d')} ~ {end_window.strftime('%Y-%m-%d')}"
    print(f"📅 데이터 탐색 기간: {window_str}")

    if not PUBLIC_API_KEY:
        return ["⚠️ PUBLIC_DATA_API_KEY가 깃허브에 설정되지 않았습니다."], window_str

    safe_key = PUBLIC_API_KEY.strip()
    encoded_key = urllib.parse.quote(safe_key)

    url_apt = f"https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail?page=1&perPage=1000&serviceKey={encoded_key}"
    url_remndr = f"https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getRemndrLttotPblancDetail?page=1&perPage=1000&serviceKey={encoded_key}"

    print("[API] 최신 클라우드 서버 직접 호출 가동...")
    apt_items = fetch_api_data(url_apt)
    remndr_items = fetch_api_data(url_remndr)
    
    if apt_items is None and remndr_items is None:
        return ["⚠️ 공공데이터포털 서버 장애로 인해 데이터를 불러올 수 없습니다."], window_str
        
    apt_items = apt_items or []
    remndr_items = remndr_items or []
    unique_results = set()

    for item in apt_items:
        name = item.get("houseNm", "").strip()
        area = item.get("hssplyAdres", "").strip()
        if not any(k in area for k in ["서울", "경기", "인천"]): continue

        przwin_de = parse_to_date(item.get("przwinPblancDe"))
        cntrct_start = parse_to_date(item.get("cntrctCnclsBgnde"))
        cntrct_end = parse_to_date(item.get("cntrctCnclsEndde"))
        spsply_start = parse_to_date(item.get("spsplyRceptBgnde"))
        spsply_end = parse_to_date(item.get("spsplyRceptEndde"))
        gnrl_start = parse_to_date(item.get("rceptBgnde"))
        gnrl_end = parse_to_date(item.get("rceptEndde"))

        # 기간 겹침 확인 (시작일이 윈도우 종료일 이전이고, 종료일이 윈도우 시작일 이후면 포함)
        if spsply_start and spsply_end and spsply_start <= end_window and spsply_end >= start_window:
            unique_results.add(f"[특공접수] {spsply_start.strftime('%m.%d')}~{spsply_end.strftime('%m.%d')} | {name} ({area})")
        if gnrl_start and gnrl_end and gnrl_start <= end_window and gnrl_end >= start_window:
            unique_results.add(f"[일반접수] {gnrl_start.strftime('%m.%d')}~{gnrl_end.strftime('%m.%d')} | {name} ({area})")
        if przwin_de and start_window <= przwin_de <= end_window:
            unique_results.add(f"[당첨발표] {przwin_de.strftime('%m.%d')} | {name} ({area})")
        if cntrct_start and cntrct_end and cntrct_start <= end_window and cntrct_end >= start_window:
            unique_results.add(f"[계약체결] {cntrct_start.strftime('%m.%d')}~{cntrct_end.strftime('%m.%d')} | {name} ({area})")

    for item in remndr_items:
        name = item.get("houseNm", "").strip()
        area = item.get("hssplyAdres", "").strip()
        if not any(k in area for k in ["서울", "경기", "인천"]): continue

        przwin_de = parse_to_date(item.get("przwinPblancDe"))
        cntrct_start = parse_to_date(item.get("cntrctCnclsBgnde"))
        cntrct_end = parse_to_date(item.get("cntrctCnclsEndde"))
        sub_start = parse_to_date(item.get("subscrptRceptBgnde"))
        sub_end = parse_to_date(item.get("subscrptRceptEndde"))

        if sub_start and sub_end and sub_start <= end_window and sub_end >= start_window:
            unique_results.add(f"[무순위접수] {sub_start.strftime('%m.%d')}~{sub_end.strftime('%m.%d')} | {name} ({area})")
        if przwin_de and start_window <= przwin_de <= end_window:
            unique_results.add(f"[당첨발표] {przwin_de.strftime('%m.%d')} | {name} ({area})")
        if cntrct_start and cntrct_end and cntrct_start <= end_window and cntrct_end >= start_window:
            unique_results.add(f"[계약체결] {cntrct_start.strftime('%m.%d')}~{cntrct_end.strftime('%m.%d')} | {name} ({area})")

    results = sorted(list(unique_results))
    print(f"🎯 [매칭 완료] 탐색 범위 내 검증 타깃 단지 수: 총 {len(results)}건")
    return results, window_str

def send_email(contents: list, window_str: str):
    no_data_keywords = ["없습니다", "없음", "오류", "실패", "누락", "⚠️"]
    no_data = not contents or any(k in contents[0] for k in no_data_keywords)

    if no_data:
        text = contents[0] if contents else f"해당 기간({window_str}) 내 수도권 아파트 공급 일정이 없습니다."
        body_html = f"<p style='color:#666;font-size:14px;font-weight:bold;text-align:center;padding:25px 0;'>ℹ️ {text}</p>"
        cnt_str = "0건"
    else:
        items_html = "".join([f"<li style='margin:14px 0;font-size:15px;font-weight:bold;color:#0056b3;border-bottom:1px dashed #eee;padding-bottom:10px;'>🏢 {item}</li>" for item in contents])
        body_html = f"<ul style='padding-left:10px;list-style-type:none;'>{items_html}</ul>"
        cnt_str = f"{len(contents)}건"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔔 [청약홈 동기화] 수도권 주간 캘린더 브리핑 ({cnt_str})"
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECEIVER_EMAIL

    html = f"""
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family:'Malgun Gothic',sans-serif;line-height:1.6;color:#333;margin:0;padding:20px;">
      <div style="max-width:700px;margin:0 auto;border:1px solid #e9ecef;border-radius:8px;overflow:hidden;box-shadow:0 4px 10px rgba(0,0,0,0.05);">
        <div style="background-color:#1a73e8;padding:24px;text-align:center;color:#fff;">
          <h2 style="margin:0;font-size:22px;font-weight:bold;letter-spacing:-0.5px;">🔔 수도권 청약 상세 캘린더</h2>
          <p style="margin:8px 0 0 0;font-size:14px;opacity:0.9;">조회기간: {window_str}</p>
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
        print("📧 이메일 발송 성공!")
    except Exception as e:
        print(f"❌ 이메일 발송 실패: {e}")

if __name__ == "__main__":
    data, window_str = get_subscription_data()
    send_email(data, window_str)
