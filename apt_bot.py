import os
import smtplib
import json
import urllib.request
import urllib.parse
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_SERVER      = "smtp.gmail.com"
SMTP_PORT        = 587
SENDER_EMAIL     = "shirou1980@gmail.com"
SENDER_PASSWORD  = os.environ.get("GMAIL_PASSWORD")
RECEIVER_EMAIL   = os.environ.get("RECEIVER_EMAIL")

def get_subscription_data():
    today = datetime.now()
    today_str = today.strftime("%Y%m%d") # 예: '20260522'
    today_day = str(today.day)
    print(f"📅 데이터 수집 기준 날짜 (한국 시간): {today.strftime('%Y-%m-%d')}")

    # 🔥 [근본적 해결책] 청약홈 서버가 달력 데이터를 불러오는 실시간 통신 주소를 직접 타격합니다.
    url = "https://www.applyhome.co.kr/ai/aia/selectAptCalenderList.do"
    
    # 청약홈 서버가 요구하는 정밀 보안 헤더값 세팅
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": "https://www.applyhome.co.kr/ai/aia/selectAptCalenderView.do"
    }
    
    # 현재 날짜 기준 한 달 치 데이터를 통째로 요청하는 파라미터 조립
    req_data = urllib.parse.urlencode({
        "searchMonth": today.strftime("%Y%m") # '202605'
    }).encode("utf-8")

    today_info = []

    try:
        print("[통신망 가로채기] 청약홈 핵심 데이터베이스 서버 요청 전송...")
        req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")
        
        with urllib.request.urlopen(req, timeout=15) as response:
            res_body = response.read().decode("utf-8")
            
        # 서버에서 받아온 순수 JSON 데이터 해석
        json_data = json.loads(res_body)
        cal_list = json_data.get("calList", [])
        
        print(f"-> 이번 달 등록된 전체 공급 일정 총 {len(cal_list)}건 확보.")
        
        for item in cal_list:
            # 아파트 정보 구조 분해
            house_nm = item.get("houseNm", "").strip()      # 아파트명
            house_secd_nm = item.get("houseSecdNm", "")    # 공급 유형 (일반, 무순위 등)
            
            # 각 단지별 고유한 스케줄 날짜들 파싱 (하이픈 제거)
            rcept_bgnde = str(item.get("rceptBgnde", "")).replace("-", "").strip() # 접수시작
            rcept_endde = str(item.get("rceptEndde", "")).replace("-", "").strip() # 접수종료
            spt_bgnde   = str(item.get("sptPblancHseRceptBgnde", "")).replace("-", "").strip() # 특공시작
            spt_endde   = str(item.get("sptPblancHseRceptEndde", "")).replace("-", "").strip() # 특공종료
            przwin_pblanc_de = str(item.get("przwinPblancDe", "")).replace("-", "").strip() # 당첨자 발표일
            cntrct_bgnde = str(item.get("cntrctBgnde", "")).replace("-", "").strip() # 계약시작일
            cntrct_endde = str(item.get("cntrctEndde", "")).replace("-", "").strip() # 계약종료일

            active_schedules = []

            # 1. 일반공급 접수 기간 체크
            if rcept_bgnde and rcept_endde and rcept_bgnde <= today_str <= rcept_endde:
                active_schedules.append("청약접수")
            # 2. 특별공급 접수 기간 체크
            if spt_bgnde and spt_endde and spt_bgnde <= today_str <= spt_endde:
                active_schedules.append("특공접수")
            # 3. 당첨자 발표일 체크
            if przwin_pblanc_de == today_str:
                active_schedules.append("당첨자발표")
            # 4. 계약 기간 체크
            if cntrct_bgnde and cntrct_endde and cntrct_bgnde <= today_str <= cntrct_endde:
                active_schedules.append("계약일")

            # 오늘 날짜에 걸려 있는 스케줄이 하나라도 있다면 리스트에 추가
            if active_schedules:
                schedule_tag = "/".join(active_schedules)
                today_info.append(f"[{schedule_tag}] {house_nm} ({house_secd_nm})")

        # 중복 제거 및 정렬
        today_info = sorted(list(set(today_info)))
        print(f"🎯 [필터링 성공] 오늘 스케줄에 걸려있는 진짜 단지 총 {len(today_info)}건 추출 완료.")

    except Exception as e:
        print(f"❌ 데이터 서버 직격 통신 중 치명적 오류 발생: {e}")
        return [f"청약홈 서버 통신 실패 (오류 코드: {e})"]

    if not today_info:
        today_info.append("오늘 예정된 아파트 청약 공급 일정이 없습니다.")
        
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
      <p>안녕하세요. <strong>""" + today_str + """</strong> 기준 오늘 달력에 등록된 전체 청약/발표/계약 일정 목록입니다.</p>
      <div style="background-color:#f8f9fa;padding:20px;border-radius:5px;border:1px solid #e9ecef;margin:20px 0;">
        """ + body_html + """
      </div>
      <p style="font-size:12px;color:#888;margin-top:30px;">본 메일은 크롤러 브라우저 없이 청약홈 정밀 데이터 통신을 통해 신속하게 발송되었습니다.</p>
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
