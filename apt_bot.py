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

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "shirou1980@gmail.com"
SENDER_PASSWORD = os.environ.get("GMAIL_PASSWORD")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL")

def get_subscription_data():
    options = Options()
    options.add_argument("--headless") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    
    driver = webdriver.Chrome(options=options)
    
    try:
        print("1. 청약홈 페이지 접속...")
        driver.get("https://www.applyhome.co.kr/ai/aia/selectAptCalenderView.do")
        time.sleep(6)
        
        # 가상 창(iframe) 진입
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "sub_iframe"))
        )
        driver.switch_to.frame("sub_iframe")
        print("-> 가상 창 내부 진입 성공")
        
        # 오늘 날짜 숫자 구하기 (예: 20)
        today_day = str(datetime.now().day)
        today_info = []
        
        print(f"2. 달력에서 오늘 날짜({today_day}일) 칸 찾는 중...")
        cells = driver.find_elements(By.CSS_SELECTOR, ".calendar_body td")
        
        target_element = None
        for cell in cells:
            # ⚠️ 오타 수정 완료: TAG_CODES -> TAG_NAME
            a_tags = cell.find_elements(By.TAG_NAME, "a")
            if a_tags:
                text_parts = cell.text.split('\n')
                if text_parts[0].strip() == today_day:
                    target_element = a_tags[0]
                    break
        
        if target_element:
            print("-> 오늘 날짜 버튼 발견! 마우스 클릭 시도...")
            driver.execute_script("arguments[0].click();", target_element)
            print("-> 클릭 완료. 데이터 로딩 대기 (7초)...")
            time.sleep(7)
        else:
            print("⚠️ 오늘 날짜 버튼을 찾지 못했습니다.")
            
        print("3. 화면 소스 긁어오기...")
        soup = BeautifulSoup(driver.page_source, "html.parser")
        list_area = soup.select_one("#sub_list_area")
        
        if list_area:
            area_text = list_area.text.strip()
            print(f"[디버깅 로그]: {area_text[:60]}")
            
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
    if not contents or "없습니다" in contents[0]:
        display_text = contents[0] if contents else "오늘 예정된 아파트 청약 접수 일정이 없습니다."
        contents_html = f"<p style='color: #666; font-size: 14px; font-weight: bold; text-align: center; padding: 10px 0;'>ℹ️ {display_text}</p>"
    else:
        list_items = "".join([f"<li style='margin: 12px 0; font-size: 15px; font-weight: bold; color: #0056b3; border-bottom: 1px dashed #eee; padding-bottom: 8px;'>🏢 {item}</li>" for item in contents])
        contents_html = f"<ul style='padding-left: 10px; list-style-type: none;'>{list_items}</ul>"
        
    today_str = datetime.now().strftime("%Y-%m-%d")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔔 [청약 알림] {today_str} 오늘의 아파트 청약 정보"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    
    html = f"""
    <html>
    <body style="font-family: 'Malgun Gothic', sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #0056b3; border-bottom: 2px solid #0056b3; padding-bottom: 10px; margin-bottom: 20px;">🏠 청약Home 오늘의 아파트 공급 정보</h2>
        <p>안녕하세요. <strong>{today_str}</strong> 기준 오늘 접수 진행 중인 아파트 목록입니다.</p>
        <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px; border: 1px solid #e9ecef; margin: 20px 0;">
            {contents_html}
        </div>
        <p style="font-size: 12px; color: #888; margin-top: 30px;">본 메일은 깃허브 자동화 서버를 통해 배달된 안내 메일입니다.</p>
    </body>
    </html>
    """
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
    print(f"📋 최종 수집 데이터 결과: {data}")
    send_email(data)
