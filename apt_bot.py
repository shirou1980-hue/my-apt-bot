import os
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

SMTP_SERVER      = "smtp.gmail.com"
SMTP_PORT        = 587
SENDER_EMAIL     = "shirou1980@gmail.com"
SENDER_PASSWORD  = os.environ.get("GMAIL_PASSWORD")
RECEIVER_EMAIL   = os.environ.get("RECEIVER_EMAIL")

def get_subscription_data():
    options = Options()
    options.add_argument("--headless") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    
    # 🔥 [진짜 핵심 치트키] 가상 브라우저의 창 크기를 일반 대형 PC 모니터 화면 크기로 박아버립니다.
    # 이렇게 해야 청약홈 달력이 모바일 모드로 쪼그라들지 않고, 아파트 이름들이 화면에 다 그려집니다.
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--start-maximized")
    
    driver = webdriver.Chrome(options=options)
    today_info = []
    
    try:
        print("1. 청약홈 달력 주소 대형 모니터 모드로 접속...")
        driver.get("https://www.applyhome.co.kr/ai/aia/selectAptCalenderView.do")
        time.sleep(8)
        
        # [1차 진입] sub_iframe
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "sub_iframe")))
        driver.switch_to.frame("sub_iframe")
        
        # [2차 진입] iframe_calendar
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "iframe_calendar")))
        driver.switch_to.frame("iframe_calendar")
        time.sleep(3)
        
        today_day = str(datetime.now().day)
        print(f"2. 전체 화면 렌더링 검증 완료. 오늘 날짜({today_day}일) 칸 정밀 크롭 시작...")
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        cells = soup.select(".calendar_body td")
        
        matched_cell = None
        for cell in cells:
            a_tag = cell.select_one("a")
            if a_tag:
                cell_day = a_tag.text.strip()
                if cell_day == today_day:
                    matched_cell = cell
                    break
        
        if matched_cell:
            print("-> [성공] 대형 달력 내부에서 오늘 날짜 구역을 확보했습니다.")
            # 텍스트 라인 단위로 쪼개서 불필요한 공백을 지우고 알맹이만 선별합니다.
            lines = [line.strip() for line in matched_cell.text.split("\n") if line.strip()]
            
            for line in lines:
                # 오늘 날짜 숫자 자체이거나, 한 글자짜리 노이즈는 제외합니다.
                if line != today_day and len(line) > 1:
                    # 완벽하게 정제된 아파트 정보 수집
                    clean_text = " ".join(line.split())
                    today_info.append(clean_text)
                    
            print(f"-> 오늘 자 일정 총 {len(today_info)}건 획득 성공.")
        else:
            print("⚠️ 반응형 해상도 우회 실패: 달력 내부에서 오늘 날짜 칸을 식별하지 못했습니다.")

        if not today_info:
            today_info.append("오늘 예정된 아파트 청약 공급 일정이 없습니다.")
            
        return today_info
        
    except Exception as e:
        print(f"❌ 크롤링 제어 중 오류 발생: {e}")
        return None
    finally:
        driver.quit()

def send_email(contents):
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
      <p>안녕하세요. <strong>""" + today_str + """</strong> 기준 오늘 달력에 등록된 청약 일정 목록입니다.</p>
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
