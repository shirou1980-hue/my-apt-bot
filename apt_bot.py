import os
import smtplib
import json
from datetime import datetime
import urllib.request
import urllib.parse
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
    today_str = today.strftime("%Y%m%d") # 예: '20260522'
    print(f"📅 수집 기준 날짜: {today.strftime('%Y-%m-%d')}")

    if not PUBLIC_API_KEY:
        print("⚠️ PUBLIC_DATA_API_KEY가 설정되지 않았습니다.")
        return ["공공데이터 API 키가 누락되었습니다. GitHub Secrets를 확인해주세요."]

    # 유효한 전국의 아파트 청약 공급 마스터 데이터를 대량 요청합니다.
    base_url = "https://apis.data.go.kr/B551011/APTLttotPblancSvc/getAPTLttotPblancMstList"
    params = urllib.parse.urlencode({
        "serviceKey" : PUBLIC_API_KEY,
        "numOfRows"        : "1000", # 누락 방지를 위해 넉넉히 설정
        "pageNo"           : "1",
        "_type"            : "json",
    })
    url = f"{base_url}?{params}"

    try:
        print("[API] 공공데이터포털 청약 마스터 데이터 수집 시작...")
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)

        body_obj = data.get("response", {}).get("body", {})
        items_data = body_obj.get("items", {})

        if not items_data or isinstance(items_data, str) or items_data == "":
            print("[API] 현재 데이터포털에 등록된 유효 청약 정보가 없습니다.")
            return ["오늘 예정된 아파트 청약 공급 일정이 없습니다."]

        items = items_data.get("item", [])
        if isinstance(items, dict):
            items = [items]

        results = []
        today_int = int(today_str)
        print(f"[API] 총 {len(items)}건의 아파트 데이터 중 오늘 자 [접수/발표/계약] 일정 정밀 매칭 시작...")

        for item in items:
            name = item.get("houseNm", "").strip()
            area = item.get("hssplyAdres", "").strip()
            
            # 1. 일반공급 및 특별공급 접수 일정 추출 (하이픈 제거)
            rcept_bgnde = item.get("rceptBgnde", "").replace("-", "").strip()
            rcept_endde = item.get("rceptEndde", "").replace("-", "").strip()
            spt_bgnde = item.get("sptPblancHseRceptBgnde", "").replace("-", "").strip()
            spt_endde = item.get("sptPblancHseRceptEndde", "").replace("-", "").strip()
            
            # 🔥 [핵심 추가] 달력 누락의 주범이었던 당첨자 발표일 및 계약 일정 변수 정밀 추적
            przwin_pblanc_de = item.get("przwinPblancDe", "").replace("-", "").strip()
            cntrct_bgnde = item.get("cntrctBgnde", "").replace("-", "").strip()
            cntrct_endde = item.get("cntrctEndde", "").replace("-", "").strip()

            active_schedules = []

            # 1) 오늘 날짜가 일반 청약 접수 기간에 걸쳐 있는지 확인
            if rcept_bgnde and rcept_endde and int(rcept_bgnde) <= today_int <= int(rcept_endde):
                active_schedules.append("일반접수")
            
            # 2) 오늘 날짜가 특별공급 접수 기간에 걸쳐 있는지 확인
            if spt_bgnde and spt_endde and int(spt_bgnde) <= today_int <= int(spt_endde):
                active_schedules.append("특공접수")
                
            # 3) 오늘이 당첨자 발표일인지 확인
            if przwin_pblanc_de and int(przwin_pblanc_de) == today_int:
                active_schedules.append("당첨자발표")
                
            # 4) 오늘 날짜가 계약 진행 기간에 걸쳐 있는지 확인
            if cntrct_bgnde and cntrct_endde and int(cntrct_bgnde) <= today_int <= int(cntrct_endde):
                active_schedules.append("계약일")

            # 네 가지 조건 중 오늘 하나라도 해당한다면 리스트에 적재
            if active_schedules:
                schedule_tag = "/".join(active_schedules)
                results.append(f"[{schedule_tag}] {name} ({area})")

        # 중복 데이터 제거 및 정렬
        results = sorted(list(set(results)))
        print(f"🎯 [매칭 완료] 오늘 일정에 해당하는 아파트 총 {len(results)}건 선별 성공.")
        return results

    except Exception as e:
        print(f"❌ API 데이터 마스터 분석 중 오류 발생: {e}")
        return [f"공공데이터 수집 중 예외 발생: {e}"]

def send_email(contents: list):
    today_str = datetime.now().strftime("%Y-%m-%d")
    no_data_keywords = ["없습니다", "없음", "오류", "실패", "누락", "예외"]
    no_data = not contents or any(k in contents[0] for k in no_data_keywords)

    if no_data:
        text = contents[0] if contents else "오늘 예정된 아파트 청약 공급 일정이 없습니다."
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
      <p>안녕하세요. <strong>""" + today_str + """</strong> 기준 오늘 진행 중인 전체 청약/발표/계약 일정 목록입니다.</p>
      <div style="background-color:#f8f9fa;padding:20px;border-radius:5px;border:1px solid #e9ecef;margin:20px 0;">
        """ + body_html + """
      </div>
      <p style="font-size:12px;color:#888;margin-top:30px;">본 메일은 안정적인 국가 공공데이터포털 API 연계를 통해 발송되었습니다.</p>
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
