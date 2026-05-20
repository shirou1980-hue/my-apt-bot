import os
import smtplib
import json
import time
from datetime import datetime
import urllib.request
import urllib.parse
# 🔥 [치명적 누락 해결] 메일 조립에 필요한 핵심 파이썬 부품들을 상단에 명시합니다.
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── 환경변수 ──────────────────────────────────────────────
SMTP_SERVER      = "smtp.gmail.com"
SMTP_PORT        = 587
SENDER_EMAIL     = "shirou1980@gmail.com"
SENDER_PASSWORD  = os.environ.get("GMAIL_PASSWORD")
RECEIVER_EMAIL   = os.environ.get("RECEIVER_EMAIL")
PUBLIC_API_KEY   = os.environ.get("PUBLIC_DATA_API_KEY", "")  # 공공데이터포털 키

def get_subscription_data() -> list:
    today = datetime.now()
    today_str = today.strftime("%Y%m%d")
    print(f"📅 수집 기준 날짜: {today.strftime('%Y-%m-%d')}")

    if not PUBLIC_API_KEY:
        print("⚠️ PUBLIC_DATA_API_KEY가 설정되지 않았습니다.")
        return ["공공데이터 API 키가 누락되었습니다. GitHub Secrets를 확인해주세요."]

    # 현재 유효한 전국의 아파트 청약 마스터 데이터를 대량 요청
    base_url = "https://apis.data.go.kr/B551011/APTLttotPblancSvc/getAPTLttotPblancMstList"
    params = urllib.parse.urlencode({
        "serviceKey" : PUBLIC_API_KEY,
        "numOfRows"        : "1000",
        "pageNo"           : "1",
        "_type"            : "json",
    })
    url = f"{base_url}?{params}"

    try:
        print("[API] 공공데이터포털 청약 마스터 데이터 로딩 중...")
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)

        body_obj = data.get("response", {}).get("body", {})
        items_data = body_obj.get("items", {})

        if not items_data or isinstance(items_data, str) or items_data == "":
            print("[API] 현재 데이터포털에 등록된 청약 정보가 없습니다.")
            return ["오늘 예정된 아파트 청약 접수 일정이 없습니다."]

        items = items_data.get("item", [])
        if isinstance(items, dict):
            items = [items]

        results = []
        today_int = int(today_str)
        print(f"[API] 총 {len(items)}건의 아파트 데이터 분석 및 오늘 자 일정 필터링 시작...")

        for item in items:
            name = item.get("houseNm", "").strip()
            area = item.get("hssplyAdres", "").strip()
            
            # 일반공급 및 특별공급 접수 일정 추출 (하이픈 제거)
            rcept_bgnde = item.get("rceptBgnde", "").replace("-", "").strip()
            rcept_endde = item.get("rceptEndde", "").replace("-", "").strip()
            
            spt_bgnde = item.get("sptPblancHseRceptBgnde", "").replace("-", "").strip()
            spt_endde = item.get("sptPblancHseRceptEndde", "").replace("-", "").strip()

            is_today_active = False
            date_info = ""

            # 1. 일반 공급 기간 체크
            if rcept_bgnde and rcept_endde:
                if int(rcept_bgnde) <= today_int <= int(rcept_endde):
                    is_today_active = True
                    date_info = f"일반접수: {rcept_bgnde} ~ {rcept_endde}"

            # 2. 특별 공급 기간 체크
            if not is_today_active and spt_bgnde and spt_endde:
                if int(spt_bgnde) <= today_int <= int(spt_endde):
                    is_today_active = True
                    date_info = f"특공접수: {spt_bgnde} ~ {spt_endde}"

            if is_today_active:
                results.append(f"{name} ({area}) | {date_info}")

        results = sorted(list(set(results)))
        print(f"🎯 [필터링 완료] 오늘 접수 중인 아파트 총 {len(results)}건 매칭 성공")
        return results

    except Exception as e:
        print(f"❌ API 데이터 마스터 분석 중 오류 발생: {e}")
        return [f"데이터 수집 중 예외 발생: {e}"]

def send_email(contents: list):
    today_str = datetime.now().strftime("%Y-%m-%d")
    no_data_keywords = ["없습니다", "없음", "오류", "실패", "누락", "예외"]
    no_data = not contents or any(k in contents[0] for k in no_data_keywords)

    if no_data:
        text = contents[0] if contents else "오늘 예정된 아파트 청약 접수 일정이 없습니다."
        body_html = "<p style='color:#666;font-size:14px;font-weight:bold;text-align:center;padding:15px 0;'>ℹ️ " + text + "</p>"
    else:
        items_html = "".join(["<li style='margin:12px 0;font-size:15px;font-weight:bold;color:#0056b3;border-bottom:1px dashed #eee;padding-bottom:8px;'>🏢 " + item + "</li>" for item in contents])
        body_html = "<ul style='padding-left:10px;list-style-type:none;'>" + items_html + "</ul>"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔔 [청약 알림] {today_str} 오늘의 아파트 청약 정보"
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECEIVER_EMAIL

    html = """
    <html>
    <body style="font-family:'Malgun Gothic',sans-serif;line-height:1.6;color:#333;">
      <h2 style="color:#0056b3;border-bottom:2px solid #0056b3;padding-bottom:10px;margin-bottom:20px;">🏠 청약Home 오늘의 아파트 공급 정보</h2>
      <p>안녕하세요. <strong>""" + today_str + """</strong> 기준 오늘 접수 진행 중인 아파트 목록입니다.</p>
      <div style="background-color:#f8f9fa;padding:20px;border-radius:5px;border:1px solid #e9ecef;margin:20px 0;">
        """ + body_html + """
      </div>
      <p style="font-size:12px;color:#888;margin-top:30px;">본 메일은 GitHub Actions 자동화 서버를 통해 발송되었습니다.</p>
    </body>
    </html>"""

    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print("📧 이메일 발송 성공!")
    except Exception as e:
        print(f"❌ 이메일 발송 실패: {e}")

if __name__ == "__main__":
    data = get_subscription_data()
    send_email(data)
