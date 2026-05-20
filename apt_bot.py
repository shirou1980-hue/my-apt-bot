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
    
    driver = webdriver.Chrome(options=options)
    today_info = []
    
    try:
        print("1. 청약홈 캘린더 직접 진입...")
        driver.get("https://www.applyhome.co.kr/ai/aia/selectAptCalenderView.do")
        time.sleep(7)
        
        # [1차] sub_iframe 진입
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "sub_iframe")))
        driver.switch_to.frame("sub_iframe")
        
        # [2차] 안쪽 달력창 진입
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "iframe_calendar")))
        driver.switch_to.frame("iframe_calendar")
        time.sleep(3)
        
        # 오늘 날짜 추출 및 클릭
        today_day = str(datetime.now().day)
        print(f"2. 달력 내부에서 오늘 날짜({today_day}일) 단추 클릭 조작...")
        
        target_xpath = f"//div[@class='calendar_body']//td//a[text()='{today_day}' or normalize-space(text())='{today_day}']"
        target_element = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, target_xpath))
        )
        
        driver.execute_script("arguments[0].click();", target_element)
        print("-> [성공] 오늘 날짜 단추를 정상 클릭했습니다.")
        print("-> 청약 데이터 통신 및 화면 로딩 대기 (7초)...")
        time.sleep(7)
        
        # [프레임 탈출] 하단 리스트 구역을 읽기 위해 부모 프레임(sub_iframe)으로 이동
        print("3. 리스트 데이터 수집을 위해 부모 프레임으로 복귀...")
        driver.switch_to.parent_frame()
        time.sleep(2)
        
        print("4. 업데이트가 완료된 최종 화면 소스 파싱 시작...")
        soup = BeautifulSoup(driver.page_source, "html.parser")
        list_area = soup.select_one("#sub_list_area")
        
        if list_area:
            area_text = list_area.text.strip()
            print(f"[서버 데이터 추출 원본]: {area_text[:60]}")
            
            if "없습니다" in area_text or not area_text:
                today_info.append("오늘 예정된 아파트 청약 접수 일정이 없습니다.")
            else:
                items = list_area.select("ul li")
                for item in items:
                    badge_el = item.select_one(".badge")
                    tit_el = item.select_one(".tit")
                    if badge_el and tit_el:
                        today_info.append(f"[{badge_el.text.strip()}] {tit_el.text.strip()}")
                        
        if not today_info:
            today_info.append("오늘 예정된 아파트 청약 접수 일정이 없습니다.")
            
        return today_info
        
    except Exception as e:
        print(f"❌ 크롤링 에러 발생: {e}")
        return None
    finally:
        driver.quit()

def send_email(contents):
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
