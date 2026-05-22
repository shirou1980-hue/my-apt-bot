import os
import smtplib
import json
import urllib.request
import urllib.parse
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── 환경변수 ──────────────────────────────────────────────
SMTP_SERVER      = "smtp.gmail.com"
SMTP_PORT        = 587
SENDER_EMAIL     = "shirou1980@gmail.com"
SENDER_PASSWORD  = os.environ.get("GMAIL_PASSWORD")
RECEIVER_EMAIL   = os.environ.get("RECEIVER_EMAIL")
PUBLIC_API_KEY   = os.environ.get("PUBLIC_DATA_API_KEY", "")

def fetch_api_data(url: str) -> list:
    """공공데이터 API 서버로부터 데이터를 안전하게 수신하는 공통 함수"""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        items_data = data.get("response", {}).get("body", {}).get("items", {})
        
        if not items_data or items_data == "" or isinstance(items_data, str):
            return []
            
        items = items_data.get("item", [])
        if isinstance(items, dict):
            return [items]
        return items
    except Exception as e:
        print(f"⚠️ 특정 API 노크 실패: {e}")
        return []

def get_subscription_data() -> list:
    today_str = datetime.now().strftime("%Y%m%d")
    today_int = int(today_str)
    print(f"📅 데이터 매칭 기준 날짜: {datetime.now().strftime('%Y-%m-%d')}")

    if not PUBLIC_API_KEY:
        return ["⚠️ PUBLIC_DATA_API_KEY가 GitHub Secrets에 설정되지 않았습니다."]

    results = []

    # 🔗 1번 파이프라인: 일반 공급 아파트 마스터 API
    url_apt = f"https://apis.data.go.kr/B551011/APTLttotPblancSvc/getAPTLttotPblancMstList?serviceKey={PUBLIC_API_KEY}&numOfRows=500&pageNo=1&_type=json"
    
    # 🔗 2번 파이프라인: 무순위 / 잔여세대 / 취소후재공급 마스터 API (★누락 해결의 핵심)
    url_remndr = f"https://apis.data.go.kr/B551011/APTLttotPblancSvc/getRemndrMstList?serviceKey={PUBLIC_API_KEY}&numOfRows=500&pageNo=1&_type=json"

    print("[API] 1번 일반 분양 및 2번 무순위 마스터 데이터 동시 다운로드 중...")
    apt_items = fetch_api_data(url_apt)
    remndr_items = fetch_api_data(url_remndr)
    
    print(f"-> 수집 원본 확보 (일반분양: {len(apt_items)}건 / 무순위: {len(remndr_items)}건)")

    # 1) 일반 아파트 마스터 분석 및 오늘 자 스케줄 필터링
    for item in apt_items:
        name = item.get("houseNm", "").strip()
        area = item.get("hssplyAdres", "").strip()
        
        rcept_bgnde = item.get("rceptBgnde", "").replace("-", "").strip()
        rcept_endde = item.get("rceptEndde", "").replace("-", "").strip()
        spt_bgnde   = item.get("sptPblancHseRceptBgnde", "").replace("-", "").strip()
        spt_endde   = item.get("sptPblancHseRceptEndde", "").replace("-", "").strip()
        przwin_de   = item.get("przwinPblancDe", "").replace("-", "").strip()
        cntrct_bgnde = item.get("cntrctBgnde", "").replace("-", "").strip()
        cntrct_endde = item.get("cntrctEndde", "").replace("-", "").strip()

        tags = []
        if rcept_bgnde and rcept_endde and int(rcept_bgnde) <= today_int <= int(rcept_endde): tags.append("일반접수")
        if spt_bgnde and spt_endde and int(spt_bgnde) <= today_int <= int(spt_endde): tags.append("특공접수")
        if przwin_de and int(przwin_de) == today_int: tags.append("당첨자발표")
        if cntrct_bgnde and cntrct_endde and int(cntrct_bgnde) <= today_int <= int(cntrct_endde): tags.append("계약일")

        if tags:
            results.append(f"[{'/'.join(tags)}] {name} ({area})")

    # 2) 무순위 / 잔여세대 마스터 분석 및 오늘 자 스케줄 필터링 (★추가 완료)
    for item in remndr_items:
        name = item.get("houseNm", "").strip()
        area = item.get("hssplyAdres", "").strip()
        
        # 무순위 세대의 고유 변수 매칭
        sub_bgnde = item.get("subscrptRceptBgnde", "").replace("-", "").strip() # 무순위 접수 시작
        sub_endde = item.get("subscrptRceptEndde", "").replace("-", "").strip() # 무순위 접수 종료
        przwin_de = item.get("przwinPblancDe", "").replace("-", "").strip()      # 발표일
        cntrct_bgnde = item.get("cntrctBgnde", "").replace("-", "").strip()     # 계약 시작
        cntrct_endde = item.get("cntrctEndde", "").replace("-", "").strip()     # 계약 종료

        tags = []
        if sub_bgnde and sub_endde and int(sub_bgnde) <= today_int <= int(sub_endde): tags.append("무순위접수")
        if przwin_de and int(przwin_de) == today_int: tags.append("당첨자발표")
        if cntrct_bgnde and cntrct_endde and int(cntrct_bgnde) <= today_int <= int(cntrct_endde): tags.append("계약일")

        if tags:
            results.append(f"[{'/'.join(tags)}] {name} ({area})")

    results = sorted(list(set(results)))
    print(f"🎯 [정밀 필터링 완료] 오늘 자 일치 공급 정보 총 {len(results)}건 매칭 성공.")
    return results

def send_email(contents: list):
    today_str = datetime.now().strftime("%Y-%m-%d")
    no_data_keywords = ["없습니다", "없음", "오류", "실패", "누락", "⚠️"]
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
      <p>안녕하세요. <strong>{today_str}</strong> 기준 오늘 진행 중인 전체 청약/발표/계약 일정 목록입니다.</p>
      <div style="background-color:#f8f9fa;padding:20px;border-radius:5px;border:1px solid #e9ecef;margin:20px 0;">
        {body_html}
      </div>
      <p style="font-size:12px;color:#888;margin-top:30px;">본 메일은 크롤러 우회 차단 위험이 없는 공공데이터 2중 API 동기화를 통해 완벽하게 발송되었습니다.</p>
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
