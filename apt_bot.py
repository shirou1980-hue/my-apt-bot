"""
청약 알림 스크립트 - 최종본 (Playwright)
- 오늘 날짜 달력 텍스트 파싱 → 아파트 목록 이메일
- 달력 스크린샷 첨부
- GitHub Actions 환경에서 안정적으로 동작
"""

import smtplib
import os
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from pathlib import Path

# ── 환경변수 (GitHub Secrets) ─────────────────────────────
SMTP_SERVER     = "smtp.gmail.com"
SMTP_PORT       = 587
SENDER_EMAIL    = "shirou1980@gmail.com"
SENDER_PASSWORD = os.environ["GMAIL_PASSWORD"]
RECEIVER_EMAIL  = os.environ["RECEIVER_EMAIL"]

TARGET_URL      = "https://www.applyhome.co.kr/ai/aia/selectAptCalenderView.do"
SCREENSHOT_PATH = Path("/tmp/apt_calendar.png")


# ── 달력 파싱 + 스크린샷 ──────────────────────────────────
def scrape_calendar() -> tuple[list[str], bool]:
    """
    반환값: (오늘 일정 텍스트 리스트, 스크린샷 성공 여부)
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    today     = datetime.now()
    today_day = str(today.day)
    today_info: list[str] = []
    screenshot_ok = False

    print(f"[{today:%H:%M:%S}] 청약홈 접속 중... (오늘: {today.month}월 {today_day}일)")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        print("  페이지 로딩...")
        page.goto(TARGET_URL, wait_until="networkidle", timeout=40000)
        page.wait_for_timeout(8000)

        # ── iframe 체인 진입 ──────────────────────────────
        # 청약홈은 메인 → sub_iframe → iframe_calendar 2중 구조
        try:
            cal = (
                page
                .frame_locator("#sub_iframe")
                .frame_locator("#iframe_calendar")
            )

            # 달력 테이블 로딩 대기
            cal.locator(".calendar_body").wait_for(timeout=30000)
            print("  달력 iframe 진입 성공")

            # ── 스크린샷 ─────────────────────────────────
            try:
                cal_wrap = cal.locator(".calendar_wrap").first
                cal_wrap.screenshot(path=str(SCREENSHOT_PATH))
                screenshot_ok = True
                print("  달력 영역 스크린샷 완료")
            except Exception as e:
                print(f"  달력 영역 스크린샷 실패, 전체 화면으로 대체: {e}")
                page.screenshot(path=str(SCREENSHOT_PATH))
                screenshot_ok = True

            # ── 오늘 날짜 칸 파싱 ────────────────────────
            # 달력의 모든 td를 순회하여 오늘 날짜 칸만 추출
            cells = cal.locator(".calendar_body td")
            count = cells.count()
            print(f"  달력 칸 수: {count}")

            for i in range(count):
                cell = cells.nth(i)
                try:
                    cell_text = cell.inner_text(timeout=2000)
                except Exception:
                    continue

                lines = [l.strip() for l in cell_text.split("\n") if l.strip()]
                if not lines:
                    continue

                # 첫 줄이 오늘 날짜 숫자인 칸
                if lines[0] == today_day:
                    print(f"  오늘({today_day}일) 칸 발견!")
                    for line in lines[1:]:          # 날짜 숫자 제외
                        clean = " ".join(line.split())
                        if len(clean) > 1:          # 노이즈 제거
                            today_info.append(clean)
                    print(f"  오늘 일정 {len(today_info)}건 파싱 완료")
                    break

        except PWTimeout:
            print("  ⚠️ iframe 타임아웃 → 전체 페이지 스크린샷으로 대체")
            page.screenshot(path=str(SCREENSHOT_PATH))
            screenshot_ok = True
        except Exception as e:
            print(f"  ⚠️ 예외 발생: {e} → 전체 페이지 스크린샷으로 대체")
            page.screenshot(path=str(SCREENSHOT_PATH))
            screenshot_ok = True

        browser.close()

    if not today_info:
        today_info.append("오늘 예정된 아파트 청약 공급 일정이 없습니다.")

    # 스크린샷 파일 유효성 확인
    if screenshot_ok:
        screenshot_ok = SCREENSHOT_PATH.exists() and SCREENSHOT_PATH.stat().st_size > 500

    return today_info, screenshot_ok


# ── 이메일 발송 ───────────────────────────────────────────
def send_email(today_info: list[str], screenshot_ok: bool):
    today    = datetime.now()
    weekdays = ['월', '화', '수', '목', '금', '토', '일']
    today_str = today.strftime("%Y-%m-%d")
    subject  = f"🔔 [청약알림] {today_str}({weekdays[today.weekday()]}) 오늘의 아파트 청약 정보"

    # 일정 목록 HTML
    no_data_kw = ["없습니다", "없음"]
    no_data    = any(kw in today_info[0] for kw in no_data_kw)

    if no_data:
        list_html = f"""
        <p style="color:#666;font-size:14px;text-align:center;padding:20px 0;">
          ℹ️ {today_info[0]}
        </p>"""
    else:
        items_html = "".join(
            f"<li style='margin:10px 0;font-size:15px;font-weight:bold;"
            f"color:#0056b3;border-bottom:1px dashed #eee;padding-bottom:8px;'>"
            f"🏢 {item}</li>"
            for item in today_info
        )
        list_html = f"<ul style='padding-left:10px;list-style:none;'>{items_html}</ul>"

    # 스크린샷 유무에 따라 img 태그 분기
    img_html = (
        '<img src="cid:calendar_image" '
        'style="width:100%;border:1px solid #ddd;border-radius:8px;margin-top:16px;display:block;">'
        if screenshot_ok else
        '<p style="color:#aaa;font-size:12px;">※ 달력 이미지를 불러오지 못했습니다.</p>'
    )

    html = f"""
    <html>
    <body style="font-family:'Malgun Gothic',sans-serif;line-height:1.6;color:#333;padding:20px;">
      <div style="max-width:900px;margin:auto;background:#fff;border-radius:12px;
                  padding:28px;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

        <h2 style="color:#0056b3;border-bottom:2px solid #0056b3;
                   padding-bottom:10px;margin-bottom:20px;">
          🏠 청약Home 오늘의 아파트 공급 정보
        </h2>

        <p>안녕하세요. <strong>{today_str}</strong> 기준
           오늘 달력에 등록된 청약 일정 목록입니다.</p>

        <div style="background:#f8f9fa;padding:20px;border-radius:8px;
                    border:1px solid #e9ecef;margin:20px 0;">
          {list_html}
        </div>

        <h3 style="color:#444;font-size:15px;margin-top:24px;">📅 이달 청약 달력</h3>
        {img_html}

        <p style="font-size:11px;color:#aaa;margin-top:24px;border-top:1px solid #eee;padding-top:10px;">
          출처: <a href="{TARGET_URL}" style="color:#0056b3;">청약홈 applyhome.co.kr</a><br>
          본 메일은 GitHub Actions 자동화 서버를 통해 발송되었습니다.
        </p>
      </div>
    </body>
    </html>"""

    # MIME 구성 (related: 인라인 이미지 포함)
    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECEIVER_EMAIL
    msg.attach(MIMEText(html, "html"))

    if screenshot_ok:
        with open(SCREENSHOT_PATH, "rb") as f:
            img = MIMEImage(f.read())
            img.add_header("Content-ID", "<calendar_image>")
            img.add_header("Content-Disposition", "inline", filename="apt_calendar.png")
            msg.attach(img)

    print(f"이메일 발송 중 → {RECEIVER_EMAIL}")
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(SENDER_EMAIL, SENDER_PASSWORD)
        smtp.send_message(msg)

    print(f"✅ 발송 완료! ({len(today_info)}건)")


# ── 진입점 ────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  청약 일정 알림 시작 (Playwright / GitHub Actions)")
    print("=" * 55)

    today_info, screenshot_ok = scrape_calendar()
    send_email(today_info, screenshot_ok)


if __name__ == "__main__":
    main()
