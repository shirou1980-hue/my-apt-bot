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

    with sync_playwright() as p:
        try:
            print("[인프라 가동] Playwright 가상 대형 PC 브라우저 런칭...")
            browser = p.chromium.launch(headless=True)
            # 대형 화면 해상도를 주입하여 반응형 모바일 모드를 강제 분쇄합니다.
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()
            
            print("-> 청약홈 메인 달력 보안 관문 진입...")
            page.goto("https://www.applyhome.co.kr/ai/aia/selectAptCalenderView.do", timeout=60000)
            
            # [1차 징검다리] sub_iframe 프레임 뼈대 장착 대기
            page.wait_for_selector("#sub_iframe", timeout=15000)
            main_frame = page.frame(name="sub_iframe")
            
            if main_frame:
                print("-> 1차 sub_iframe 진입 성공. 내부 달력 렌더링 감시단 가동...")
                # 2차 내부 달력 프레임 뼈대가 완전히 구성될 때까지 추적 대기
                main_frame.wait_for_selector("#iframe_calendar", timeout=15000)
                
                calendar_frame = None
                for f in main_frame.child_frames:
                    if f.name == "iframe_calendar":
                        calendar_frame = f
                        break
                
                if calendar_frame:
                    # 🔥 [진짜 최종 근본 해결책: 물리 텍스트 로딩 정밀 감시]
                    # 단순히 sleep으로 노는 것이 아니라, 달력 칸 내부(.calendar_body td)에 아파트 텍스트 정보가 
                    # 한 줄이라도 브라우저 메모리에 완벽하게 그려져서 렌더링될 때까지 물리적으로 대기합니다.
                    print("-> [정밀 동기화] 달력 내부에 진짜 청약 데이터 글자가 인쇄될 때까지 대기 감시 중...")
                    try:
                        calendar_frame.wait_for_selector(".calendar_body td a, .calendar_body font", timeout=20000)
                        print("-> [감시 성공] 청약홈 진짜 알맹이 데이터 렌더링 완벽 포착!")
                    except:
                        print("⚠️ 정밀 감시 타임아웃: 안전 수집을 위해 추가 시간 정지(5초)를 부여합니다.")
                        time.sleep(5)
                        
                    html_content = calendar_frame.content()
                else:
                    html_content = page.content()
            else:
                html_content = page.content()

            print("-> 달력 소스 내부 텍스트 복사 및 필터링 오려내기 시작...")
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
                print(f"-> [성공] 오늘({today_day}일) 자 칸 구역 확보 완료.")
                raw_lines = [line.strip() for line in matched_cell.get_text(separator="\n").split("\n") if line.strip()]
                
                for line in raw_lines:
                    if line != today_day and len(line) > 1:
                        clean_text = " ".join(line.split())
                        today_info.append(clean_text)
            else:
                print("⚠️ 달력 내부에서 오늘 날짜 구역 파싱을 전면 놓쳤습니다.")

        except Exception as e:
            print(f"❌ 매크로 제어 엔진 작동 중 예외 발생: {e}")
            return [f"청약홈 매크로 제어 예외 발생: {e}"]
        finally:
            browser.close()

    today_info = sorted(list(set(today_info)))
    print(f"📋 최종 빌드된 메일 발송 데이터 목록: {today_info}")
    
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
      <p style="font-size:12px;color:#888;margin-top:30px;">본 메일은 인프라 타이밍 레이더 감시 구문이 심어진 최종 안정화 엔진을 통해 발송되었습니다.</p>
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
