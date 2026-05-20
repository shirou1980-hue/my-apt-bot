import os
import smtplib
import json
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── 환경변수 ──────────────────────────────────────────────
SMTP_SERVER      = "smtp.gmail.com"
SMTP_PORT        = 587
SENDER_EMAIL     = "shirou1980@gmail.com"
SENDER_PASSWORD  = os.environ.get("GMAIL_PASSWORD")
RECEIVER_EMAIL   = os.environ.get("RECEIVER_EMAIL")
PUBLIC_API_KEY   = os.environ.get("PUBLIC_DATA_API_KEY", "")  # 공공데이터포털 키

# ══════════════════════════════════════════════════════════
# 방법 1: 공공데이터포털 API (안정적 방어 로직 적용)
# ══════════════════════════════════════════════════════════
def fetch_via_public_api(today: datetime) -> list | None:
    if not PUBLIC_API_KEY:
        print("⚠️ PUBLIC_DATA_API_KEY 없음 → 크롤링 폴백")
        return None

    import urllib.request
    import urllib.parse

    date_str = today.strftime("%Y%m%d")
    base_url = "https://apis.data.go.kr/B551011/APTLttotPblancSvc/getAPTLttotPblancList"

    params = urllib.parse.urlencode({
        "serviceKey" : PUBLIC_API_KEY,
        "startSubscrptDate": date_str,
        "endSubscrptDate"  : date_str,
        "houseSecd"        : "01",    # 01=아파트
        "numOfRows"        : "100",
        "pageNo"           : "1",
        "_type"            : "json",
    })
    url = f"{base_url}?{params}"

    try:
        print("[API] 요청 시도 중...")
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)

        response_obj = data.get("response", {})
        header_obj = response_obj.get("header", {})
        body_obj = response_obj.get("body", {})

        if header_obj.get("resultCode") != "00":
            print(f"[API] 서버 응답 오류: {header_obj.get('resultMsg')}")
            return None

        # 데이터가 없을 때 빈 문자열("") 또는 빈 딕셔너리로 오는 현상 완벽 방어
        items_data = body_obj.get("items", {})
        if not items_data or isinstance(items_data, str) or items_data == "":
            print("[API] 오늘 기준 검색된 청약 단지가 없습니다. (정상 반환)")
            return []

        items = items_data.get("item", [])
        if isinstance(items, dict):
            items = [items]

        print(f"[API] 결과 {len(items)}건 발견")
        results = []
        for item in items:
            name    = item.get("houseNm", "")
            area    = item.get("hssplyAdres", "")
            start   = item.get("rceptBgnde", "")
            end     = item.get("rceptEndde", "")
            results.append(f"{name} ({area}) | 접수: {start} ~ {end}")

        return results

    except Exception as e:
        print(f"[API] 예외 발생: {e}")
        return None

# ══════════════════════════════════════════════════════════
# 방법 2: Playwright 크롤링 (안정화 폴백)
# ══════════════════════════════════════════════════════════
def fetch_via_playwright(today: datetime) -> list:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ playwright 패키지가 시스템에 설치되어 있지 않습니다.")
        return ["Playwright 패키지 미설치로 크롤링을 생략합니다."]

    today_day = str(today.day)
    results   = []

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--single-process"]
            )
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            print("[PW] 청약홈 가상 접속 시작...")
            page.goto("https://www.applyhome.co.kr/ai/aia/selectAptCalenderView.do", wait_until="lazy", timeout=30000)
            page.wait_for_timeout(5000)

            sub_frame = page.frame(name="sub_iframe")
            if not sub_frame:
                return ["청약홈 sub_iframe 구조 탐색 실패"]

            cal_frame = sub_frame.frame(name="iframe_calendar")
            if not cal_frame:
                return ["청약홈 iframe_calendar 구조 탐색 실패"]

            target_xpath = f"//div[@class='calendar_body']//td//a[text()='{today_day}' or normalize-space(text())='{today_day}']"
            try:
                cal_frame.click(f"xpath={target_xpath}", timeout=5000)
                page.wait_for_timeout(5000)
            except:
                pass

            html = sub_frame.content()
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            list_area = soup.select_one("#sub_list_area")

            if list_area:
                area_text = list_area.get_text(strip=True)
                no_data = ["없습니다", "없음", "결과가 없", "데이터가 없"]
                if area_text and not any(k in area_text for k in no_data):
                    items = list_area.select("ul > li")
                    for item in items:
                        badge = item.select_one(".badge")
                        tit   = item.select_one(".tit")
                        if badge and tit:
                            results.append(f"[{badge.get_text(strip=True)}] {tit.get_text(strip=True)}")
            browser.close()
        except Exception as pw_err:
            print(f"[PW] 크롤링 도중 오류: {pw_err}")
            
    return results

# ══════════════════════════════════════════════════════════
# 메인 제어 루틴
# ══════════════════════════════════════════════════════════
def get_subscription_data() -> list:
    today = datetime.now()
    print(f"📅 수집 기준 날짜: {today.strftime('%Y-%m-%d')}")

    data = fetch_via_public_api(today)

    if data is None:
        print("→ API 장애 또는 인증 오류로 Playwright 크롤링 폴백 진행...")
        data = fetch_via_playwright(today)

    if not data:
        data = ["오늘 예정된 아파트 청약 접수 일정이 없습니다."]

    return data

# ══════════════════════════════════════════════════════════
# 이메일 발송 루틴 (변수 선언 오류 해결 완료)
# ══════════════════════════════════════════════════════════
def send_email(contents: list):
    # 🔥 [핵심 수정] 함수가 시작되자마자 최우선으로 날짜 변수부터 완벽하게 선언합니다.
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    no_data_keywords = ["없습니다", "없음", "오류", "실패", "패키지"]
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

    # f-string 충돌 우려가 없는 깔끔한 문자열 결합 방식 유지
    html = """
    <html>
    <body style="font-family:'Malgun Gothic',sans-serif;line-height:1.6;color:#333;">
      <h2 style="color:#0056b3;border-bottom:2px solid #0056b3;padding-bottom:10px;margin-bottom:20px;">🏠 청약Home 오늘의 아파트 공급 정보</h2>
      <p>안녕하세요. <strong>""" + today_str + """</strong> 기준 공급 진행 중인 아파트 목록입니다.</p>
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
    print(f"\n📋 최종 결과 데이터: {data}")
    send_email(data)
