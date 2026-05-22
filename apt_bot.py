import os
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

SMTP_SERVER      = "smtp.gmail.com"
SMTP_PORT        = 587
SENDER_EMAIL     = "shirou1980@gmail.com"
SENDER_PASSWORD  = os.environ.get("GMAIL_PASSWORD")
RECEIVER_EMAIL   = os.environ.get("RECEIVER_EMAIL")

def get_subscription_data():
    today = datetime.now()
    today_day = str(today.day)
    print(f"📅 데이터 수집 기준 날짜 (한국 시간): {today.strftime('%Y-%m-%d')}")

    today_info = []

    # 🔥 Playwright를 켜서 청약홈 내부 보안 프레임과 비동기 데이터를 완벽하게 렌더링합니다.
    with sync_playwright() as p:
        try:
            print("[인프라 가동] Playwright 가상 대형 PC 브라우저 구동...")
            # 대형 화면 해상도를 강제 주입하여 모바일 달력으로 쪼그라드는 것을 원천 차단합니다.
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()
            
            print("-> 청약홈 메인 달력 주소 진입 중...")
            page.goto("https://www.applyhome.co.kr/ai/aia/selectAptCalenderView.do", timeout=60000)
            
            # 🔥 [가장 중요] 가상 서버의 네트워크 딜레이를 감안하여 화면이 완전히 그려질 때까지 12초간 대기합니다.
            print("-> 청약홈 보안 프레임 및 달력 데이터 최종 로딩 대기 (12초)...")
            time.sleep(12)
            
            # 2중 iframe의 장벽을 뚫고 내부 진짜 달력 알맹이 코드를 강제 획득합니다.
            print("-> 2중 보안 프레임 우회 및 달력 HTML 소스 크롭 시작...")
            
            # 1차 sub_iframe 진입 후 안쪽 2차 iframe_calendar 진입
            main_frame = page.frame(name="sub_iframe")
            if main_frame:
                calendar_frame = main_frame.child_frames[0] if main_frame.child_frames else main_frame
                for f in main_frame.child_frames:
                    if f.name == "iframe_calendar":
                        calendar_frame = f
                        break
                
                html_content = calendar_frame.content()
            else:
                # 프레임 구조가 안 잡힐 경우 전체 페이지 긁기 백업
                html_content = page.content()

            soup = BeautifulSoup(html_content, "html.parser")
            cells = soup.select(".calendar_body td, table td")
            print(f"-> 검색된 달력 그리드 칸 수: {len(cells)}개")
            
            matched_cell = None
            for cell in cells:
                cell_text = cell.get_text(separator=" ", strip=True)
                lines = [l.strip() for l in cell_text.split() if l.strip()]
                
                if lines and lines[0] == today_day:
                    matched_cell = cell
                    break
                    
            if matched_cell:
                print(f"-> [성공] 대형 달력 내부에서 오늘({today_day}일) 자 데이터 구역 매칭 성공!")
                raw_lines = [line.strip() for line in matched_cell.get_text(separator="\n").split("\n") if line.strip()]
                
                for line in raw_lines:
                    # 오늘 날짜 숫자 자체이거나 노이즈 제거
                    if line != today_day and len(line) > 1:
                        clean_text = " ".join(line.split())
                        today_info.append(clean_text)
            else:
                print("⚠️ 달력 소스 내부에서 오늘 날짜 칸을 최종 식별하지 못했습니다.")

        except Exception as e:
            print(f"❌ 크롤링 매크로 구동 중 치명적 예외 발생: {e}")
            return [f"청약홈 시스템 제어 에러 발생: {e}"]
        finally:
            browser.close()

    # 중복 제거 및 정렬
    today_info = sorted(list(set(today_info)))
    
    if not today_info:
        today_info.append("오늘 예정된 아파트 청약 공급 일정이 없습니다.")
        
    return today_info

def send_email(contents):
    today_str = datetime.now().strftime("%Y-%m-%d")
    no_data_keywords = ["없습니다", "없음", "오류", "실패", "누락"]
    no_data = not contents or any(k in contents[0] for k in no_data_keywords)

    if no_data:
        text = contents[0] if contents else "오늘 예정된 아파트 청약 공급 일정이 없습니다."
        body_html = f"<p style='color:#666;font-size:14px;font-weight:bold;text-align:center;padding:15px 0;'>ℹ️ {text}</p>"
    else:
        items_html = "".join([f"<li style='margin:12px 0;font-size:15px;font-weight:bold;color:#0056b3;border-bottom:1px dashed #eee;padding-bottom:8px;'>🏢 {item}</li>" for item in contents])
        body_html = f"<ul style='padding-left:10px;list-style-type:none;'>{items_html}</ul>"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔔 [청약 알림] {today_str} 오늘의 아파트 청약 정보"
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECEIVER_EMAIL

    html = f"""
    <html>
    <body style="font-family:'Malgun Gothic',sans-serif;line-height:1.6;color:#333;">
      <h2 style="color:#0056b3;border-bottom:2px solid #0056b3;padding-bottom:10px;margin-bottom:20px;">🏠 청약Home 오늘의 아파트 공급 정보</h2>
      <p>안녕하세요. <strong>{today_str}</strong> 기준 오늘 달력에 등록된 전체 일정 목록입니다.</p>
      <div style="background-color:#f8f9fa;padding:20px;border-radius:5px;border:1px solid #e9ecef;margin:20px 0;">
        {body_html}
      </div>
      <p style="font-size:12px;color:#888;margin-top:30px;">본 메일은 인프라 환경이 완벽히 검증된 Playwright 무결점 매크로 엔진을 통해 발송되었습니다.</p>
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
