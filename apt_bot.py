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
    if not date_str: return None
    clean_str = str(date_str).replace("-", "").strip()
    if len(clean_str) >= 8:
        try: return datetime.strptime(clean_str[:8], "%Y%m%d")
        except: return None
    return None

def get_val(item, keys: list) -> str:
    for k in keys:
        if k in item and item[k] is not None:
            return str(item[k]).strip()
    return ""

def fetch_all_pages(base_url: str, retries=3) -> list:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json'
    }
    all_data = []
    page = 1
    
    while page <= 10:
        url = f"{base_url}&page={page}&perPage=1000"
        success = False
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=20) as resp:
                    raw = resp.read().decode("utf-8")
                resp_json = json.loads(raw)
                if "data" in resp_json and resp_json["data"]:
                    all_data.extend(resp_json["data"])
                    success = True
                break
            except HTTPError: time.sleep(2)
            except Exception: time.sleep(2)
        if not success: break
        page += 1
    return all_data

def add_events_to_calendar(start_d, end_d, event_type, name, events_by_date, start_window, end_window):
    """일정 기간(Start~End)을 달력의 각 날짜에 블록으로 채워넣는 함수"""
    if not start_d or not end_d: return
    curr = start_d
    while curr <= end_d:
        if start_window <= curr <= end_window:
            d_str = curr.strftime('%Y-%m-%d')
            if d_str not in events_by_date:
                events_by_date[d_str] = []
            # 중복 방지
            if not any(e['name'] == name and e['type'] == event_type for e in events_by_date[d_str]):
                events_by_date[d_str].append({'type': event_type, 'name': name})
        curr += timedelta(days=1)

def get_subscription_data() -> tuple:
    today = datetime.utcnow() + timedelta(hours=9)
    today = today.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 캘린더 표현을 위해 오늘 기준 이전 1주 ~ 이후 2주 (총 3주) 탐색
    start_window = today - timedelta(days=7)
    end_window = today + timedelta(days=14)
    window_str = f"{start_window.strftime('%Y-%m-%d')} ~ {end_window.strftime('%Y-%m-%d')}"

    if not PUBLIC_API_KEY:
        return {}, window_str, start_window, end_window

    safe_key = PUBLIC_API_KEY.strip()
    encoded_key = urllib.parse.quote(safe_key)

    url_apt = f"https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail?serviceKey={encoded_key}"
    url_remndr = f"https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getRemndrLttotPblancDetail?serviceKey={encoded_key}"

    apt_items = fetch_all_pages(url_apt)
    remndr_items = fetch_all_pages(url_remndr)
    
    events_by_date = {}

    # 1. 일반 분양 (특공, 1·2순위)
    for item in apt_items:
        name = get_val(item, ["houseNm", "HOUSE_NM", "house_nm"])
        area = get_val(item, ["hssplyAdres", "HSSPLY_ADRES", "hssply_adres"])
        # 🔥 서울, 경기 지역만 필터링 (인천 등 제외)
        if not any(k in area for k in ["서울", "경기"]): continue

        spsply_start = parse_to_date(get_val(item, ["spsplyRceptBgnde", "SPSPLY_RCEPT_BGNDE"]))
        spsply_end = parse_to_date(get_val(item, ["spsplyRceptEndde", "SPSPLY_RCEPT_ENDDE"]))
        gnrl_start = parse_to_date(get_val(item, ["rceptBgnde", "RCEPT_BGNDE"]))
        gnrl_end = parse_to_date(get_val(item, ["rceptEndde", "RCEPT_ENDDE"]))

        add_events_to_calendar(spsply_start, spsply_end, '특별공급', name, events_by_date, start_window, end_window)
        add_events_to_calendar(gnrl_start, gnrl_end, '1·2순위', name, events_by_date, start_window, end_window)

    # 2. 무순위 / 임의공급 / 취소후재공급
    for item in remndr_items:
        name = get_val(item, ["houseNm", "HOUSE_NM", "house_nm"])
        area = get_val(item, ["hssplyAdres", "HSSPLY_ADRES", "hssply_adres"])
        if not any(k in area for k in ["서울", "경기"]): continue

        sub_start = parse_to_date(get_val(item, ["subscrptRceptBgnde", "SUBSCRPT_RCEPT_BGNDE"]))
        sub_end = parse_to_date(get_val(item, ["subscrptRceptEndde", "SUBSCRPT_RCEPT_ENDDE"]))
        
        # 무순위/임의공급 여부는 API 특성상 명칭으로 추정하거나 일괄 무순위로 표기
        event_type = '무순위'
        if '취소분' in name or '재공급' in name: event_type = '취소후재공급'
        elif '임의' in name: event_type = '임의공급'

        add_events_to_calendar(sub_start, sub_end, event_type, name, events_by_date, start_window, end_window)

    return events_by_date, window_str, start_window, end_window

def build_html_calendar(events_by_date, start_window, end_window):
    # 달력 시작일(월요일)과 종료일(일요일) 맞추기
    cal_start = start_window - timedelta(days=start_window.weekday())
    cal_end = end_window + timedelta(days=(6 - end_window.weekday()))

    html = "<table style='width:100%; border-collapse: collapse; table-layout: fixed; min-width: 600px; font-family: sans-serif;'>"
    html += "<thead><tr>"
    days = ['월', '화', '수', '목', '금', '토', '일']
    for d in days:
        color = "red" if d == '일' else "blue" if d == '토' else "#333"
        html += f"<th style='border: 1px solid #dee2e6; padding: 10px 5px; background: #f8f9fa; font-size: 13px; color: {color}; width: 14%;'>{d}</th>"
    html += "</tr></thead><tbody><tr>"

    curr = cal_start
    while curr <= cal_end:
        if curr.weekday() == 0 and curr != cal_start:
            html += "</tr><tr>" # 새로운 주(Week) 행 바꿈

        date_str = curr.strftime('%Y-%m-%d')
        day_num = curr.day
        day_color = "red" if curr.weekday() == 6 else "blue" if curr.weekday() == 5 else "#495057"
        
        # 오늘 날짜 하이라이트
        is_today = (curr == datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=9))
        bg_td = "#fffdf0" if is_today else "#ffffff"

        html += f"<td style='border: 1px solid #dee2e6; padding: 5px; vertical-align: top; height: 110px; background-color: {bg_td};'>"
        html += f"<div style='font-weight: bold; font-size: 12px; margin-bottom: 5px; color: {day_color};'>{day_num}</div>"

        if date_str in events_by_date:
            for event in events_by_date[date_str]:
                bg_color, text_color, border = "#ffffff", "#333", "1px solid #dee2e6"
                
                # 청약홈 UI 카테고리별 색상 매핑
                if event['type'] == '특별공급':
                    bg_color, text_color, border = "#ff8c00", "#fff", "none" # 주황색
                elif event['type'] == '1·2순위':
                    bg_color, text_color, border = "#0d6efd", "#fff", "none" # 파란색
                elif event['type'] in ['무순위', '임의공급', '취소후재공급']:
                    bg_color, text_color, border = "#ffffff", "#495057", "1px solid #ced4da" # 테두리

                short_type = event['type'][:2] # 특공, 1·, 무순 등으로 축약
                if event['type'] == '1·2순위': short_type = '1순위' # 시각적 간결함
                
                html += f"""
                <div style='background-color: {bg_color}; color: {text_color}; border: {border}; border-radius: 3px; padding: 3px; font-size: 11px; margin-bottom: 4px; line-height: 1.2; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; word-break: break-all;' title='[{event['type']}] {event['name']}'>
                    <strong>{short_type}</strong> {event['name']}
                </div>
                """
        html += "</td>"
        curr += timedelta(days=1)

    html += "</tr></tbody></table>"
    return html

def send_email(events_by_date: dict, window_str: str, start_window, end_window):
    has_data = any(events_by_date.values())
    
    if not has_data:
        cal_html = f"<p style='text-align:center; padding: 30px; color: #666;'>해당 기간({window_str}) 내 서울/경기 지역 아파트 공급 일정이 없습니다.</p>"
    else:
        cal_html = build_html_calendar(events_by_date, start_window, end_window)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔔 [청약홈] 서울/경기 주간 캘린더 브리핑"
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECEIVER_EMAIL

    html = f"""
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family:'Malgun Gothic',sans-serif;line-height:1.6;color:#333;margin:0;padding:20px; background-color: #f4f6f9;">
      <div style="max-width:850px;margin:0 auto;border:1px solid #e9ecef;border-radius:8px;overflow:hidden;box-shadow:0 4px 10px rgba(0,0,0,0.05); background-color: #fff;">
        <div style="background-color:#1a73e8;padding:20px;text-align:center;color:#fff;">
          <h2 style="margin:0;font-size:20px;font-weight:bold;">📅 서울/경기 청약 상세 캘린더</h2>
          <p style="margin:5px 0 0 0;font-size:13px;opacity:0.9;">조회기간: {window_str}</p>
        </div>
        <div style="padding:20px; overflow-x: auto;">
          {cal_html}
        </div>
        <div style="background-color:#f8f9fa;padding:12px;text-align:center;font-size:11px;color:#888;border-top:1px solid #e9ecef;">
          ■ 특별공급(주황) ■ 1·2순위(파랑) □ 무순위/임의(테두리)
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
        print("📧 캘린더 이메일 발송 성공!")
    except Exception as e:
        print(f"❌ 이메일 발송 실패: {e}")

if __name__ == "__main__":
    events, w_str, s_win, e_win = get_subscription_data()
    send_email(events, w_str, s_win, e_win)
