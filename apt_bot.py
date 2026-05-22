import os
import smtplib
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── 환경변수 ──────────────────────────────────────────────
SMTP_SERVER     = "smtp.gmail.com"
SMTP_PORT       = 587
SENDER_EMAIL    = "shirou1980@gmail.com"
SENDER_PASSWORD = os.environ.get("GMAIL_PASSWORD")
RECEIVER_EMAIL  = os.environ.get("RECEIVER_EMAIL")
RAW_API_KEY     = os.environ.get("PUBLIC_DATA_API_KEY", "")

# ★ 핵심 수정 1: 공공데이터 API 키는 반드시 디코딩된 원본(URL에 %2B 등 이미 인코딩된)을 사용해야 함.
#   포털에서 발급받은 키가 이미 인코딩된 형태라면 그대로 쓰고,
#   디코딩된 원본 키라면 아래처럼 quote()로 인코딩해서 URL에 삽입.
def encode_api_key(key: str) -> str:
    """공공데이터 API 키를 URL-safe 하게 인코딩 (이중 인코딩 방지)"""
    # 이미 %XX 형태로 인코딩된 키는 디코딩 후 재인코딩
    try:
        decoded = urllib.parse.unquote(key)
        return urllib.parse.quote(decoded, safe='')
    except Exception:
        return urllib.parse.quote(key, safe='')


def fetch_api_data(url: str, label: str = "") -> list:
    """공공데이터 API 호출 공통 함수 - 에러 코드까지 정밀 검증"""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 AptBot/2.0"}
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")

        # ★ 핵심 수정 2: XML 에러 응답 감지 (API 키 오류 등)
        if raw.strip().startswith("<"):
            print(f"⚠️ [{label}] XML 오류 응답 수신 (API 키 문제 가능성):\n{raw[:300]}")
            return []

        data = json.loads(raw)
        header = data.get("response", {}).get("header", {})
        result_code = header.get("resultCode", "00")
        result_msg  = header.get("resultMsg", "")

        # ★ 핵심 수정 3: resultCode 검증
        if result_code != "00":
            print(f"⚠️ [{label}] API 오류 코드={result_code}, 메시지={result_msg}")
            return []

        body       = data.get("response", {}).get("body", {})
        total_count = body.get("totalCount", 0)
        print(f"   [{label}] totalCount={total_count}")

        items_data = body.get("items", {})
        if not items_data or items_data == "":
            return []

        items = items_data.get("item", [])

        # ★ 핵심 수정 4: 단일 아이템이 dict로 올 때 처리
        if isinstance(items, dict):
            return [items]
        if isinstance(items, list):
            return items
        return []

    except json.JSONDecodeError as e:
        print(f"⚠️ [{label}] JSON 파싱 실패: {e}")
        return []
    except Exception as e:
        print(f"⚠️ [{label}] API 호출 실패: {e}")
        return []


def safe_date(val) -> str:
    """날짜값을 YYYYMMDD 문자열로 정규화. 실패 시 빈 문자열 반환"""
    if not val:
        return ""
    return str(val).replace("-", "").strip()


def is_in_range(start_str: str, end_str: str, target_int: int) -> bool:
    """날짜 범위 내 포함 여부 검사 - 변환 실패 시 False"""
    try:
        if not start_str or not end_str:
            return False
        return int(start_str) <= target_int <= int(end_str)
    except ValueError:
        return False


def is_exact(date_str: str, target_int: int) -> bool:
    """특정 날짜 일치 여부 - 변환 실패 시 False"""
    try:
        if not date_str:
            return False
        return int(date_str) == target_int
    except ValueError:
        return False


def get_subscription_data() -> dict:
    """
    오늘 진행 중인 청약 정보 + 향후 7일 내 시작 예정 청약 조회.
    반환: {"today": [...], "upcoming": [...], "errors": [...]}
    """
    today     = datetime.now()
    today_int = int(today.strftime("%Y%m%d"))
    week_later_int = int((today + timedelta(days=7)).strftime("%Y%m%d"))

    print(f"📅 기준 날짜: {today.strftime('%Y-%m-%d')} (오늘={today_int}, 7일후={week_later_int})")

    if not RAW_API_KEY:
        return {"today": [], "upcoming": [], "errors": ["⚠️ PUBLIC_DATA_API_KEY가 GitHub Secrets에 없습니다."]}

    API_KEY = encode_api_key(RAW_API_KEY)
    base_params = f"numOfRows=1000&pageNo=1&_type=json"

    # ★ 수정 5: 날짜 범위 파라미터 추가 (일부 API는 범위 필터 지원)
    # 향후 30일치 데이터를 가져와 클라이언트 측에서 필터링
    endpoints = {
        "일반분양": f"https://apis.data.go.kr/B551011/APTLttotPblancSvc/getAPTLttotPblancMstList?serviceKey={API_KEY}&{base_params}",
        "무순위/잔여": f"https://apis.data.go.kr/B551011/APTLttotPblancSvc/getRemndrMstList?serviceKey={API_KEY}&{base_params}",
    }

    today_results    = []
    upcoming_results = []

    for label, url in endpoints.items():
        print(f"\n🔗 [{label}] API 호출 중...")
        items = fetch_api_data(url, label)
        print(f"   수집 건수: {len(items)}건")

        for item in items:
            name = item.get("houseNm", "").strip() or item.get("houseName", "").strip()
            area = item.get("hssplyAdres", "").strip()
            if not name:
                continue

            # 날짜 필드 수집 (일반분양 / 무순위 공용)
            fields = {
                "특공접수":   (safe_date(item.get("sptPblancHseRceptBgnde")), safe_date(item.get("sptPblancHseRceptEndde"))),
                "일반접수":   (safe_date(item.get("rceptBgnde")), safe_date(item.get("rceptEndde"))),
                "무순위접수": (safe_date(item.get("subscrptRceptBgnde")), safe_date(item.get("subscrptRceptEndde"))),
                "계약":       (safe_date(item.get("cntrctBgnde")), safe_date(item.get("cntrctEndde"))),
            }
            przwin_de    = safe_date(item.get("przwinPblancDe"))
            mvn_presmde  = safe_date(item.get("mvnPresmde", ""))  # 입주예정일(참고용)

            today_tags    = []
            upcoming_tags = []

            for tag, (s, e) in fields.items():
                if is_in_range(s, e, today_int):
                    today_tags.append(tag)
                elif s and is_in_range(str(today_int + 1), e or s, week_later_int) and int(s) >= today_int:
                    # 오늘 이후 ~ 7일 내 시작 예정
                    try:
                        if today_int < int(s) <= week_later_int:
                            upcoming_tags.append(f"{tag}(~{s[4:6]}/{s[6:8]}시작)")
                    except ValueError:
                        pass

            if is_exact(przwin_de, today_int):
                today_tags.append("당첨자발표")
            elif przwin_de:
                try:
                    if today_int < int(przwin_de) <= week_later_int:
                        upcoming_tags.append(f"당첨자발표({przwin_de[4:6]}/{przwin_de[6:8]})")
                except ValueError:
                    pass

            entry = f"[{label}] {name} / {area}"

            if today_tags:
                today_results.append(f"[{'·'.join(today_tags)}] {name} ({area})")
            if upcoming_tags:
                upcoming_results.append(f"[{'·'.join(upcoming_tags)}] {name} ({area})")

    today_results    = sorted(set(today_results))
    upcoming_results = sorted(set(upcoming_results))

    print(f"\n🎯 오늘 일치: {len(today_results)}건 / 향후 7일 예정: {len(upcoming_results)}건")
    return {"today": today_results, "upcoming": upcoming_results, "errors": []}


def build_html_body(today: list, upcoming: list) -> str:
    today_str = datetime.now().strftime("%Y-%m-%d")

    def make_list_html(items, color):
        if not items:
            return f"<p style='color:#888;text-align:center;padding:10px;'>해당 없음</p>"
        rows = "".join([
            f"<li style='margin:10px 0;font-size:14px;color:{color};border-bottom:1px dashed #e0e0e0;padding-bottom:8px;'>"
            f"🏢 {item}</li>"
            for item in items
        ])
        return f"<ul style='padding-left:10px;list-style:none;'>{rows}</ul>"

    today_html    = make_list_html(today, "#0056b3")
    upcoming_html = make_list_html(upcoming, "#c05000")

    return f"""
    <html>
    <body style="font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;line-height:1.7;color:#333;max-width:700px;margin:0 auto;">
      <h2 style="color:#0056b3;border-bottom:3px solid #0056b3;padding-bottom:10px;">
        🏠 청약Home 오늘의 아파트 공급 정보
      </h2>
      <p>안녕하세요. <strong>{today_str}</strong> 기준 청약 일정 알림입니다.</p>

      <h3 style="color:#0056b3;margin-top:25px;">📌 오늘 진행 중인 청약</h3>
      <div style="background:#f0f4ff;padding:15px;border-radius:6px;border:1px solid #ccd6f0;">
        {today_html}
      </div>

      <h3 style="color:#c05000;margin-top:25px;">📅 향후 7일 내 시작 예정</h3>
      <div style="background:#fff8f0;padding:15px;border-radius:6px;border:1px solid #f0d6b0;">
        {upcoming_html}
      </div>

      <p style="font-size:11px;color:#aaa;margin-top:30px;border-top:1px solid #eee;padding-top:10px;">
        ※ 본 메일은 공공데이터포털 청약 API (APTLttotPblancSvc)를 통해 자동 발송되었습니다.<br>
        ※ 실제 청약 일정은 청약Home(applyhome.co.kr)에서 반드시 확인하세요.
      </p>
    </body>
    </html>"""


def send_email(result: dict):
    today_str   = datetime.now().strftime("%Y-%m-%d")
    today_list  = result.get("today", [])
    upcoming_list = result.get("upcoming", [])
    errors      = result.get("errors", [])

    if errors:
        # 에러 발생 시 에러 내용 메일 발송
        html = f"<p style='color:red;'>{errors[0]}</p>"
    else:
        html = build_html_body(today_list, upcoming_list)

    subject = f"🔔 [청약알림] {today_str} - 오늘 {len(today_list)}건 / 7일내 {len(upcoming_list)}건"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECEIVER_EMAIL
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print(f"📧 이메일 발송 성공! 제목: {subject}")
    except Exception as e:
        print(f"❌ 이메일 발송 실패: {e}")
        raise


if __name__ == "__main__":
    result = get_subscription_data()
    send_email(result)
