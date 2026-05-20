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
    
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    
    try:
        print("1. 청약홈 메인 세션 생성 중...")
        driver.get("https://www.applyhome.co.kr/co/coa/selectMainView.do")
        time.sleep(5)
        
        print("2. 청약 캘린더 페이지 진입...")
        driver.get("https://www.applyhome.co.kr/ai/aia/selectAptCalenderView.do")
        time.sleep(5)
        
        # 🔥 [진짜 핵심 수정] 청약홈 달력은 'sub_iframe'이라는 가상 창 안에 들어있습니다.
        # 가상 창이 생길 때까지 기다렸다가, 로봇의 중심(포커스)을 그 안으로 순간이동 시킵니다!
        print("-> [보안 우회] 투명 가상 화면(iframe) 탐색 및 침투 중...")
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.ID, "sub_iframe"))
        )
        driver.switch_to.frame("sub_iframe")
        print("-> [성공] 가상 내부 화면 진입 완료!")
        
        # 내부 가상 화면 안에서 달력 뼈대가 떴는지 다시 확인합니다.
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CLASS_NAME, "calendar_body"))
        )
        time.sleep(3)
        
        target_date = datetime.now().strftime("%Y%m%d")
        today_info = []
        
        print(f"3. 가상 내부 화면에서 직접 데이터 요청 명령 주입 ({target_date})...")
        driver.execute_script(f"setCalenderDetailList('{target_date}')")
        time.sleep(5)
        
        print("4. 갱신된 하단 데이터 추출 시작...")
        soup = BeautifulSoup(driver.page_source, "html.parser")
        list_area = soup.select_one("#sub_list_area")
        
        if list_area:
            area_text = list_area.text.strip()
            print(f"[서버 확인 로그]: {area_text[:60]}")
            
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
        print(f"❌ 크롤링 실패 원인: {e}")
        return None
    finally:
        driver.quit()

def send_email(contents):
    if not contents or "없습니다" in contents[0]:
        display_text = contents[0] if contents else "오늘 예정된 아파트 청약 접수 일정이 없습니다."
        contents_html = f"<p style='color: #666; font-size: 14px; font-weight: bold; text-align: center; padding: 10px 0;'>ℹ️ {display_text}</p>"
    else:
        list_items = "".join([f"<li style='margin: 10px 0; font-size: 15px; font-weight: bold; color: #e65c00;'>🏢 {item}</li>" for item in contents])
        contents_html = f"<ul style='padding-left: 20px; list-style-type: none;'>{list_items}</ul>"
        
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
