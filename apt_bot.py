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

# ──────────────────────────────────────────
# 환경변수 설정
# ──────────────────────────────────────────
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "shirou1980@gmail.com"
SENDER_PASSWORD = os.environ.get("GMAIL_PASSWORD")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL")


def make_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def safe_switch_frame(driver, frame_id, timeout=20):
    """특정 id의 iframe으로 안전하게 진입"""
    WebDriverWait(driver, timeout).until(
        EC.frame_to_be_available_and_switch_to_it((By.ID, frame_id))
    )
    time.sleep(1)


def dump_html_for_debug(driver, label=""):
    """디버깅용 현재 프레임 HTML 덤프 (처음 2000자)"""
    try:
        src = driver.page_source
        print(f"\n{'='*20} [{label}] HTML 미리보기 {'='*20}")
        print(src[:2000])
        print("=" * 60)
    except Exception as e:
        print(f"[{label}] HTML 덤프 실패: {e}")


def get_subscription_data():
    driver = make_driver()
    today = datetime.now()
    today_day = str(today.day)          # e.g. "20"
    today_str = today.strftime("%Y-%m-%d")
    today_info = []

    try:
        # ── 1. 사이트 진입 ─────────────────────────────────────
        print("1. 청약홈 달력 접속 중...")
        driver.get("https://www.applyhome.co.kr/ai/aia/selectAptCalenderView.do")
        time.sleep(5)

        # ── 2. sub_iframe 진입 ────────────────────────────────
        print("2. sub_iframe 진입...")
        safe_switch_frame(driver, "sub_iframe")

        # ── 3. iframe_calendar 진입 ───────────────────────────
        print("3. iframe_calendar 진입...")
        safe_switch_frame(driver, "iframe_calendar")
        time.sleep(2)

        # [디버그] 달력 내부 HTML 확인
        dump_html_for_debug(driver, "달력 내부")

        # ── 4. 오늘 날짜 클릭 ────────────────────────────────
        print(f"4. 오늘({today_day}일) 날짜 클릭 시도...")

        # 여러 XPath 패턴을 순서대로 시도
        xpaths = [
            f"//td[contains(@class,'today')]//a",           # today 클래스가 있으면 우선
            f"//div[contains(@class,'calendar_body')]//td//a[normalize-space(text())='{today_day}']",
            f"//table//td//a[normalize-space(text())='{today_day}']",
            f"//a[normalize-space(text())='{today_day}']",
        ]

        clicked = False
        for xpath in xpaths:
            try:
                el = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                driver.execute_script("arguments[0].click();", el)
                print(f"   ✅ 클릭 성공: {xpath}")
                clicked = True
                break
            except Exception:
                continue

        if not clicked:
            print("   ⚠️ 날짜 클릭 실패 - 첫 번째 날짜 링크 클릭 시도...")
            links = driver.find_elements(By.XPATH, "//td//a")
            if links:
                driver.execute_script("arguments[0].click();", links[0])
                print(f"   ✅ 대체 클릭 성공 (text={links[0].text.strip()})")

        time.sleep(3)

        # ── 5. 최상위 프레임으로 완전 복귀 ──────────────────
        #    [핵심 수정] parent_frame() → default_content()
        #    parent_frame()은 sub_iframe으로 돌아가지만,
        #    sub_iframe 안의 list_area DOM은 selenium이 읽지 못함.
        #    해결: iframe_calendar를 닫고 sub_iframe 안에서 직접 파싱.
        print("5. sub_iframe으로 복귀 (parent_frame)...")
        driver.switch_to.parent_frame()   # iframe_calendar → sub_iframe
        time.sleep(5)                      # 리스트 갱신 대기

        # [디버그] 리스트 영역 HTML 확인
        dump_html_for_debug(driver, "sub_iframe 복귀 후")

        # ── 6. 리스트 파싱 ───────────────────────────────────
        print("6. 아파트 청약 리스트 파싱...")
        soup = BeautifulSoup(driver.page_source, "html.parser")

        # 가능한 셀렉터 목록 (사이트 구조 변경에 대응)
        list_area = (
            soup.select_one("#sub_list_area")
            or soup.select_one(".list_wrap")
            or soup.select_one("#calList")
            or soup.select_one(".calender_list")
        )

        if list_area:
            area_text = list_area.get_text(strip=True)
            print(f"   [리스트 텍스트 미리보기]: {area_text[:120]}")

            no_data_keywords = ["없습니다", "없음", "데이터가 없", "조회된 결과가 없"]
            if not area_text or any(kw in area_text for kw in no_data_keywords):
                today_info.append(f"{today_str} 오늘 예정된 아파트 청약 접수 일정이 없습니다.")
            else:
                # 다양한 아이템 구조 대응
                items = list_area.select("ul > li") or list_area.select(".item") or list_area.select("tr")
                print(f"   아이템 수: {len(items)}")

                for item in items:
                    # 패턴 1: badge + tit (기존 구조)
                    badge_el = item.select_one(".badge, .type, .state")
                    tit_el   = item.select_one(".tit, .name, .apt_name, td")

                    if badge_el and tit_el:
                        badge = badge_el.get_text(strip=True)
                        title = tit_el.get_text(strip=True)
                        today_info.append(f"[{badge}] {title}")

                    # 패턴 2: badge 없이 텍스트만 있는 경우
                    elif not badge_el and tit_el:
                        title = item.get_text(separator=" ", strip=True)
                        if title:
                            today_info.append(title)

        else:
            print("   ⚠️ 리스트 영역을 찾지 못함 - 전체 페이지 텍스트 확인")
            # 리스트 영역 못 찾을 경우 전체에서 아파트 관련 텍스트 추출 시도
            all_text = soup.get_text(separator="\n", strip=True)
            print(f"   전체 텍스트 미리보기:\n{all_text[:500]}")
            today_info.append("리스트 영역 파싱 실패 - 사이트 구조를 확인하세요.")

        if not today_info:
            today_info.append(f"{today_str} 오늘 예정된 아파트 청약 접수 일정이 없습니다.")

        return today_info

    except Exception as e:
        import traceback
        print(f"❌ 크롤링 에러:\n{traceback.format_exc()}")
        return [f"크롤링 중 오류 발생: {e}"]
    finally:
        driver.quit()


def send_email(contents: list):
    today_str = datetime.now().strftime("%Y-%m-%d")

    no_data = not contents or any(
        kw in contents[0] for kw in ["없습니다", "없음", "오류 발생", "파싱 실패"]
    )

    if no_data:
        display_text = contents[0] if contents else "오늘 예정된 아파트 청약 접수 일정이 없습니다."
        contents_html = (
            f"<p style='color:#666;font-size:14px;font-weight:bold;"
            f"text-align:center;padding:15px 0;'>ℹ️ {display_text}</p>"
        )
    else:
        list_items = "".join(
            [
                f"<li style='margin:12px 0;font-size:15px;font-weight:bold;"
                f"color:#0056b3;border-bottom:1px dashed #eee;padding-bottom:8px;'>"
                f"🏢 {item}</li>"
                for item in contents
            ]
        )
        contents_html = (
            f"<ul style='padding-left:10px;list-style-type:none;'>{list_items}</ul>"
        )

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
    {contents_html}
  </div>
  <p style="font-size:12px;color:#888;margin-top:30px;">
    본 메일은 GitHub Actions 자동화 서버를 통해 발송된 안내 메일입니다.
  </p>
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
    print(f"\n📋 최종 수집 결과: {data}")
    send_email(data)
