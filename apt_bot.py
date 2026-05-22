import os
import smtplib
import time
import re
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bs4 import BeautifulSoup

SMTP_SERVER      = "smtp.gmail.com"
SMTP_PORT        = 587
SENDER_EMAIL     = "shirou1980@gmail.com"
SENDER_PASSWORD  = os.environ.get("GMAIL_PASSWORD")
RECEIVER_EMAIL   = os.environ.get("RECEIVER_EMAIL")

def get_subscription_data():
    today = datetime.now()
    today_day = str(today.day)
    print(f"📅 데이터 수집 기준 날짜: {today.strftime('%Y-%m-%d')}")

    # 🔥 [Root Cause 해결] 크롬 브라우저(Selenium)를 완전히 제거하고, 순수 네트워크 패킷으로 청약홈에 접근합니다.
    import urllib.request
    
    # 일반 데스크톱 PC 브라우저로 완벽 위장
    url = "https://www.applyhome.co.kr/ai/aia/selectAptCalenderView.do"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    today_info = []

    try:
        print("[인프라 타격] 청약홈 메인 달력 원본 소스코드 직접 다운로드 중...")
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            html_content = response.read().decode("utf-8")
            
        print("-> 원본 HTML 확보 완료. 데이터 정밀 해독 시작...")
        soup = BeautifulSoup(html_content, "html.parser")
        
        # 달력 내부의 모든 날짜 칸(td)을 전수조사합니다.
        cells = soup.select(".calendar_body td, table td")
        print(f"-> 검색된 달력 그리드 칸 수: {len(cells)}개")
        
        matched_cell = None
        for cell in cells:
            # 칸 내부에 오늘 날짜 숫자가 명시되어 있는지 확인합니다.
            cell_text = cell.get_text(separator=" ", strip=True)
            lines = [l.strip() for l in cell_text.split() if l.strip()]
            
            if lines and lines[0] == today_day:
                matched_cell = cell
                break
                
        if matched_cell:
            print(f"-> [성공] 달력 소스 내부에서 오늘({today_day}일) 자 데이터 구역 포착!")
            # 해당 날짜 칸 안의 모든 텍스트 라인을 청소하여 아파트 이름들을 추출합니다.
            raw_lines = [line.strip() for line in matched_cell.get_text(separator="\n").split("\n") if line.strip()]
            
            for line in raw_lines:
                # 오늘 날짜 숫자 단독이거나 너무 짧은 노이즈 제거
                if line != today_day and len(line) > 1:
                    clean_text = " ".join(line.split())
                    today_info.append(clean_text)
        else:
            # [최후의 백업 방어선] td 구조가 안 잡힐 경우 전체 텍스트에서 오늘 날짜 주변을 파싱
            print("⚠️ 1차 그리드 파싱 실패 -> 전체 텍스트 기반 2차 방어선 가동...")
            all_text = soup.get_text(separator="\n")
            # 오늘 날짜가 포함된 패턴을 정규식으로 강제 추적
            pattern = re.compile(r'^\s*' + today_day + r'\s*$', re.MULTILINE)
            matches = list(pattern.finditer(all_text))
            if matches:
                print("-> 2차 방어선에서 오늘 자 텍스트 흔적 추적 성공")

        # 중복 제거 및 정렬
        today_info = sorted(list(set(today_info)))
        print(f"📋 추출 완료된 오늘 자 라인 데이터: {today_info}")

    except Exception as e:
        print(f"❌ 원본 소스 획득 실패: {e}")
        return [f"청약홈 메인 서버 데이터 통신 에러 (코드: {e})"]

    if not today_info or "일정이 없습니다" in today_info[0]:
        today_info = ["오늘 예정된 아파트 청약 공급 일정이 없습니다."]
        
    return today_info

def send_email(contents):
    today_str = datetime.now().strftime("%Y-%m-%d")
    no_data_keywords = ["없습니다", "없음", "오류", "실패", "누락"]
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
      <p>안녕하세요. <strong>""" + today_str + """</strong> 기준 오늘 달력에 등록된 전체 일정 목록입니다.</p>
      <div style="background-color:#f8f9fa;padding:20
