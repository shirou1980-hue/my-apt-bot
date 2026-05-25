import os
import smtplib
import json
import urllib.request
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── 환경변수 ──────────────────────────────────────────────
SMTP_SERVER      = "smtp.gmail.com"
SMTP_PORT        = 587
SENDER_EMAIL     = "shirou1980@gmail.com"
SENDER_PASSWORD  = os.environ.get("GMAIL_PASSWORD")
RECEIVER_EMAIL   = os.environ.get("RECEIVER_EMAIL")
PUBLIC_API_KEY   = os.environ.get("PUBLIC_DATA_API_KEY", "")

def parse_to_date(date_str: str):
    """다양한 날짜 포맷(하이픈 유무 등)을 파이썬 datetime 객체로 안전하게 변환"""
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

def get_subscription_data() -> list:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    print(f"📅 데이터 필터링 기준 날짜: {today.strftime('%Y-%m-%d')}")

    if not PUBLIC_API_KEY:
        return ["⚠️ PUBLIC_DATA_API_KEY가 설정되지 않았습니다."]

    results = []

    # 2중 파이프라인 마스터 데이터 동시 타격
    url_apt = f"https://apis.data.go.kr/B551011/APTLttotPblancSvc/getAPTLttotPblancMstList?serviceKey={PUBLIC_API_KEY}&numOfRows=1000&pageNo=1&_type=json"
    url_remndr = f"https://apis.data.go.kr/B551011/APTLttotPblancSvc/getRemndrMstList?serviceKey={PUBLIC_API_KEY}&numOfRows=1000&pageNo=1&_type=json"

    print("[API] 정부 청약 데이터베이스 연계 호출 시작...")
    apt_items = fetch_api_data(url_apt)
    remndr_items = fetch_api_data(url_remndr)

    # 1) 일반 아파트 마스터 정밀 필터링
    for item in apt_items:
        name = item.get("houseNm", "").strip()
        area = item.get("hssplyAdres", "").strip()
        
        # 수도권(서울, 경기, 인천) 데이터만 선별하기 위한 가드닝 코드
        if not any(k in area for k in ["서울", "경기", "인천"]):
            continue

        rcept_bgnde = parse_to_date(item.get("rceptBgnde"))
        rcept_endde = parse_to_date(item.get("rceptEndde"))
        spt_bgnde   = parse_to_date(item.get("sptPblancHseRceptBgnde"))
        spt_endde   = parse_to_date(item.get("sptPblancHseRceptEndde"))
        przwin_de   = parse_to_date(item.get("przwinPblancDe"))
        cntrct_bgnde = parse_to_date(item.get("cntrctBgnde"))
        cntrct_endde = parse_to_date(item.get("cntrctEndde"))

        tags = []
        if rcept_bgnde and rcept_endde and rcept_bgnde <= today <= rcept_endde: tags.append("일반접수")
        if spt_bgnde and spt_endde and spt_bgnde <= today <= spt_endde: tags.append("특공접수")
        if przwin_de and przwin_de == today: tags.append("당첨자발표")
        if cntrct_bgnde and cntrct_endde and cntrct_bgnde <= today <= cntrct_endde: tags.append("계약일")

        if tags:
            results.append(f"[{'/'.join(tags)}] {name} ({area})")

    # 2) 무순위 / 잔여세대 마스터 정밀 필터링
    for item in remndr_items:
        name = item.get("houseNm", "").strip()
        area = item.get("hssplyAdres", "").strip()
        
        if not any(k in area for k in ["서울", "경기", "인천"]):
            continue

        sub_bgnde = parse_to_date(item.get("subscrptRceptBgnde"))
        sub_endde = parse_to_date(item.get("subscrptRceptEndde"))
        przwin_de = parse_to_date(item.get("przwinPblancDe"))
        cntrct_bgnde = parse_to_date(item.get("cntrctBgnde"))
        cntrct_endde = parse_to_date(item.get("cntrctEndde"))

        tags = []
        if sub_bgnde and sub_endde and sub_bgnde <= today <= sub_endde: tags.append("무순위접수")
        if przwin_de and przwin_de == today: tags.append("당첨자발표")
        if cntrct_bgnde and cntrct_endde and cntrct_bgnde <= today <= cntrct_endde: tags.append("계약일")

        if tags:
            results.append(f"[{'/'.join(tags)}] {name} ({area})")

    results = sorted(list(set(results)))
    print(f"🎯 [수도권 동기화 완료] 오늘 유효 일정: 총 {len(results)}건 매칭")
    return results

def send_email(contents: list):
    today_str = datetime.now().strftime("%Y-%m-%d")
    no_data_keywords = ["없습니다", "없음", "오류", "실패", "누락", "⚠️"]
    no_data = not contents or any(k in contents[0] for k in no_data_keywords)

    if no_data:
        body_html = "<p style='color:#666;font-size:14px;font-weight:bold;text-align:center;padding:25px 0;'>ℹ️ 오늘 진행 중인 수도권 아파트 공급 일정이 없습니다.</p>"
        cnt_str = "0건"
    else:
        items_html = "".join([f"<li style='margin:14px 0;font-size:15px;font-weight:bold;color:#0056b3;border-bottom:1px dashed #eee;padding-bottom:10px;'>🏢 {item}</li>" for item in contents])
        body_html = f"<ul style='padding-left:10px;list-style-type:none;'>{items_html}</ul>"
        cnt_str = f"{len(contents)}건"

    msg = MIMEMultipart("alternative")
    # 🔥 이메일 제목과 송신자 선언부 인코딩 깨짐을 완벽하게 예방
    msg["Subject"] = f"🔔 [청약홈 동기화] 수도권 정밀 캘린더 ({cnt_str})"
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECEIVER_EMAIL

    html = f"""
    <html>
    <head>
      <meta charset="utf-8">
    </head>
    <body style="font-family:'Malgun Gothic',sans-serif;line-height:1.6;color:#333;margin:0;padding:20px;">
      <div style="max-width:700px;margin:0 auto;border:1px solid #e9ecef;border-radius:8px;overflow:hidden;box-shadow:0 4px 10px rgba(0,0,0,0.05);">
        <div style="background-color:#1a73e8;padding:24px;text-align:center;color:#fff;">
          <h2 style="margin:0;font-size:22px;font-weight:bold;letter-spacing:-0.5px;">🔔 수도권 청약 상세 캘린더</h2>
          <p style="margin:8px 0 0 0;font-size:14px;opacity:0.9;">기준일자: {today_str}</p>
        </div>
        <div style="padding:24px;background-color:#fff;">
          {body_html}
        </div>
        <div style="background-color:#f8f9fa;padding:15px;text-align:center;font-size:12px;color:#888;border-top:1px solid #e9ecef;">
          본 메일은 안전한 공공데이터포털 연계 인프라를 통해 자동 생성 및 발송되었습니다.
        </div>
      </div>
    </body>
    </html>"""

    # 🔥 메일 본문 삽입 시 utf-8 인코딩 명시로 다이아몬드 물음표 차단
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
