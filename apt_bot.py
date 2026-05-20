"""
청약홈 아파트 청약 알림 메일 발송 스크립트
- 1순위: 공공데이터포털 API (가장 안정적, API 키 필요)
- 2순위: Playwright 크롤링 (API 키 없을 때 자동 폴백)

환경변수 설정 (GitHub Actions Secrets):
  GMAIL_PASSWORD   : Gmail 앱 비밀번호
  RECEIVER_EMAIL   : 수신 이메일
  PUBLIC_DATA_API_KEY : 공공데이터포털 API 키 (없으면 Playwright 폴백)
"""

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
# 방법 1: 공공데이터포털 API (안정적, 추천)
# ══════════════════════════════════════════════════════════
def fetch_via_public_api(today: datetime) -> list | None:
    """
    공공데이터포털 아파트분양정보서비스 API 호출
    https://www.data.go.kr/data/15069119/openapi.do
    """
    if not PUBLIC_API_KEY:
        print("⚠️  PUBLIC_DATA_API_KEY 없음 → Playwright 폴백")
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
        print(f"[API] 요청: {url[:120]}...")
        with urllib.request.urlopen(url, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)

        items = (
            data.get("response", {})
                .get("body", {})
                .get("items", {})
                .get("item", [])
        )
        # 단일 결과면 dict로 오는 경우 처리
        if isinstance(items, dict):
            items = [items]

        print(f"[API] 결과 {len(items)}건")
        results = []
        for item in items:
            name    = item.get("houseNm", "")
            area    = item.get("hssplyAdres", "")
            start   = item.get("rceptBgnde", "")
            end     = item.get("rceptEndde", "")
            kind    = item.get("houseSecd", "")
            results.append(f"[{kind}] {name} ({area}) | 접수: {start}~{end}")

        return results if results else []

    except Exception as e:
        print(f"[API] 오류: {e}")
        return None


# ══════════════════════════════════════════════════════════
# 방법 2: Playwright 크롤링 (폴백)
# ══════════════════════════════════════════════════════════
def fetch_via_playwright(today: datetime) -> list:
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("❌ playwright 미설치. pip install playwright && playwright install chromium")
        return ["playwright 패키지가 설치되지 않았습니다."]

    today_day = str(today.day)
    results   = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process",        # ← GitHub Actions 크래시 방지 핵심
                "--no-zygote",
                "--disable-setuid-sandbox",
            ],
        )
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )

        try:
            print("[PW] 청약홈 접속...")
            page.goto(
                "https://www.applyhome.co.kr/ai/aia/selectAptCalenderView.do",
                wait_until="networkidle",
                timeout=30000,
            )
            page.wait_for_timeout(4000)

            # ── sub_iframe 진입 ──────────────────────────
            print("[PW] sub_iframe 진입...")
            sub_frame = page.frame(name="sub_iframe") or page.frame(url=lambda u: "sub_iframe" in u)
            if not sub_frame:
                frames = page.frames
                print(f"[PW] 사용 가능한 프레임: {[f.name for f in frames]}")
                sub_frame = frames[1] if len(frames) > 1 else None

            if not sub_frame:
                print("[PW] sub_iframe 없음")
                return ["sub_iframe 프레임을 찾을 수 없습니다."]

            # ── iframe_calendar 진입 ─────────────────────
            print("[PW] iframe_calendar 진입...")
            cal_frame = sub_frame.frame(name="iframe_calendar")
            if not cal_frame:
                all_frames = sub_frame.child_frames
                print(f"[PW] sub_iframe 하위 프레임: {[f.name for f in all_frames]}")
                cal_frame = all_frames[0] if all_frames else None

            if not cal_frame:
                print("[PW] iframe_calendar 없음")
                return ["iframe_calendar 프레임을 찾을 수 없습니다."]

            # ── 오늘 날짜 클릭 ───────────────────────────
            print(f"[PW] {today_day}일 클릭...")
            xpaths = [
                f"//td[contains(@class,'today')]//a",
                f"//div[contains(@class,'calendar_body')]//td//a[normalize-space()='{today_day}']",
                f"//table//td//a[normalize-space()='{today_day}']",
            ]
            clicked = False
            for xp in xpaths:
                try:
                    cal_frame.click(f"xpath={xp}", timeout=5000)
                    print(f"[PW] 클릭 성공: {xp}")
                    clicked = True
                    break
                except PWTimeout:
                    continue

            if not clicked:
                print("[PW] 날짜 클릭 실패 - 현재 달력 HTML 덤프:")
                print(cal_frame.content()[:1500])
                return ["날짜 클릭 실패 - 달력 구조 변경 가능성"]

            # ── 리스트 갱신 대기 ─────────────────────────
            page.wait_for_timeout(5000)

            # ── sub_frame 에서 리스트 파싱 ──────────────
            print("[PW] 리스트 파싱...")
            html = sub_frame.content()
            print(f"[PW] sub_frame HTML 미리보기:\n{html[:1500]}")

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            list_area = (
                soup.select_one("#sub_list_area")
                or soup.select_one(".list_wrap")
                or soup.select_one("#calList")
            )

            if list_area:
                area_text = list_area.get_text(strip=True)
                no_data   = ["없습니다", "없음", "결과가 없", "데이터가 없"]
                if not area_text or any(k in area_text for k in no_data):
                    results = []
                else:
                    items = list_area.select("ul > li") or list_area.select(".item")
                    for item in items:
                        badge = item.select_one(".badge, .type, .state")
                        tit   = item.select_one(".tit, .name, .apt_name")
                        if badge and tit:
                            results.append(f"[{badge.get_text(strip=True)}] {tit.get_text(strip=True)}")
                        else:
                            txt = item.get_text(separator=" ", strip=True)
                            if txt:
                                results.append(txt)
            else:
                print("[PW] 리스트 영역 없음 - 전체 HTML:")
                print(html[:3000])

        except Exception as e:
            import traceback
            print(f"[PW] 오류:\n{traceback.format_exc()}")
            results = [f"Playwright 크롤링 오류: {e}"]
        finally:
            browser.close()

    return results


# ══════════════════════════════════════════════════════════
# 메인 데이터 수집
# ══════════════════════════════════════════════════════════
def get_subscription_data() -> list:
    today = datetime.now()
    print(f"📅 수집 날짜: {today.strftime('%Y-%m-%d')}")

    # 1순위: 공공 API
    data = fetch_via_public_api(today)

    # 2순위: Playwright
    if data is None:
        print("→ Playwright 크롤링으로 폴백...")
        data = fetch_via_playwright(today)

    if not data:
        data = [f"{today.strftime('%Y-%m-%d')} 오늘 예정된 아파트 청약 접수 일정이 없습니다."]

    return data


# ══════════════════════════════════════════════════════════
# 이메일 발송
# ══════════════════════════════════════════════════════════
def send_email(contents: list):
    today_str = today_str = datetime.now().strftime("%Y-%m-%d")
    no_data_keywords = ["없습니다", "없음", "오류", "실패", "패키지"]
    no_data = not contents or any(k in contents[0] for k in no_data_keywords)

    if no_data:
        text = contents[0] if contents else "오늘 예정된 아파트 청약 접수 일정이 없습니다."
        body_html = (
            f"<p style='color:#666;font-size:14px;font-weight:bold;"
            f"text-align:center;padding:15px 0;'>ℹ️ {text}</p>"
        )
    else:
        items_html = "".join(
            f"<li style='margin:12px 0;font-size:15px;font-weight:bold;"
            f"color:#0056b3;border-bottom:1px dashed #eee;padding-bottom:8px;'>"
            f"🏢 {item}</li>"
            for item in contents
        )
        body_html = f"<ul style='padding-left:10px;list-style-type:none;'>{items_html}</ul>"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔔 [청약 알림] {today_str} 오늘의 아파트 청약 정보"
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECEIVER_EMAIL

    html = f"""
<html>
<body style="font-family:'Malgun Gothic',sans-serif;line-height:1.6;color:#333;">
  <h2 style="color:#0056b3;border-bottom:2px solid #0056b3;
             padding-bottom:10px;margin-bottom:20px;">
    🏠 청약Home 오늘의 아파트 공급 정보
  </h2>
  <p>안녕하세요. <strong>{today_str}</strong> 기준 오늘 접수 진행 중인 아파트 목록입니다.</p>
  <div style="background-color:#f8f9fa;padding:20px;border-radius:5px;
              border:1px solid #e9ecef;margin:20px 0;">
    {body_html}
  </div>
  <p style="font-size:12px;color:#888;margin-top:30px;">
    본 메일은 GitHub Actions 자동화 서버를 통해 발송된 안내 메일입니다.
  </p>
</body>
</html>"""

    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print("📧 이메일 발송 완료!")
    except Exception as e:
        print(f"❌ 이메일 발송 실패: {e}")


if __name__ == "__main__":
    data = get_subscription_data()
    print(f"\n📋 최종 결과: {data}")
    send_email(data)
