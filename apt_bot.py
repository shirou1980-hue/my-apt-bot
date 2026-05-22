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

# ★ 핵심: 공공데이터 키는 포털에서 발급한 "인코딩된 키"를 그대로 써야 한다.
#   urllib이 URL을 조합할 때 serviceKey를 또 인코딩하면 이중 인코딩 → 키 깨짐.
#   해결책: URL 문자열을 직접 조립(f-string)하고, 키는 미리 디코딩 후 재인코딩하여 고정.
def prepare_key(raw: str) -> str:
    """포털 발급 키(인코딩 여부 무관)를 URL-safe 단일 인코딩으로 정규화"""
    try:
        decoded = urllib.parse.unquote(raw)   # 이미 인코딩된 키 → 디코딩
        return urllib.parse.quote(decoded, safe='')  # 재인코딩(단일)
    except Exception:
        return raw


def fetch_raw(url: str, label: str) -> dict:
    """URL을 직접 호출 후 JSON dict 반환. 실패 시 {} 반환"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 AptBot/3.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode("utf-8")
    except Exception as e:
        print(f"  [{label}] 연결 실패: {e}")
        return {}

    # XML 에러 응답 감지 (API 키 오류 시 XML로 내려옴)
    stripped = raw.strip()
    if stripped.startswith("<"):
        print(f"  [{label}] ⚠️ XML 에러 응답 수신 → API 키 문제 가능성")
        print(f"  내용: {stripped[:300]}")
        return {}

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  [{label}] JSON 파싱 실패: {e}")
        print(f"  원문(200자): {raw[:200]}")
        return {}


def call_api(url: str, label: str) -> list:
    """
    공공데이터 API를 호출하여 item 리스트 반환.
    ★ 핵심: API는 '모집공고일(pblancBgnde ~ pblancEndde)' 기준으로만 데이터를 돌려줌.
       날짜 범위를 넓게(30~90일) 잡아서 전체를 내려받고, 파이썬 측에서 오늘 날짜 필터링.
    """
    data = fetch_raw(url, label)
    if not data:
        return []

    resp   = data.get("response", {})
    header = resp.get("header", {})
    code   = header.get("resultCode", "")
    msg    = header.get("resultMsg", "")

    if code != "00":
        print(f"  [{label}] API 오류 resultCode={code} / {msg}")
        return []

    body        = resp.get("body", {})
    total_count = body.get("totalCount", 0)
    print(f"  [{label}] totalCount={total_count}")

    if total_count == 0:
        return []

    items_wrap = body.get("items")
    if not items_wrap or items_wrap == "":
        return []

    items = items_wrap.get("item", [])
    if isinstance(items, dict):   # 단건 조회 시 dict로 내려옴
        items = [items]
    return items if isinstance(items, list) else []


def sd(val) -> str:
    """날짜값 → YYYYMMDD 문자열. 실패 시 ''"""
    if not val:
        return ""
    return str(val).replace("-", "").strip()


def in_range(s: str, e: str, t: int) -> bool:
    """t가 [s, e] 범위 내인지 (문자열 → int 변환, 실패 시 False)"""
    try:
        return bool(s) and bool(e) and int(s) <= t <= int(e)
    except (ValueError, TypeError):
        return False


def exact(d: str, t: int) -> bool:
    try:
        return bool(d) and int(d) == t
    except (ValueError, TypeError):
        return False


def get_subscription_data() -> dict:
    today      = datetime.now()
    today_int  = int(today.strftime("%Y%m%d"))
    # 공고일 범위: 60일 전 ~ 60일 후 (오늘 기준 진행 중인 청약을 모두 포괄)
    from_dt    = (today - timedelta(days=60)).strftime("%Y%m%d")
    to_dt      = (today + timedelta(days=60)).strftime("%Y%m%d")
    week_later = int((today + timedelta(days=7)).strftime("%Y%m%d"))

    print(f"📅 기준일: {today.strftime('%Y-%m-%d')} | 조회범위: {from_dt} ~ {to_dt}")

    if not RAW_API_KEY:
        return {"today": [], "upcoming": [], "errors": ["⚠️ PUBLIC_DATA_API_KEY가 설정되지 않았습니다."]}

    KEY = prepare_key(RAW_API_KEY)

    # ★★★ 핵심 수정: pblancBgnde / pblancEndde 파라미터 추가 ★★★
    # 이 API는 날짜 범위를 반드시 줘야 데이터를 돌려줌.
    # 날짜 없이 호출 → totalCount=0 (빈 응답) 반환하는 구조.
    common_params = f"numOfRows=1000&pageNo=1&_type=json&pblancBgnde={from_dt}&pblancEndde={to_dt}"

    endpoints = {
        "일반분양": (
            f"https://apis.data.go.kr/B551011/APTLttotPblancSvc/"
            f"getAPTLttotPblancMstList?serviceKey={KEY}&{common_params}",
            # 날짜 필드 매핑 (필드명: (시작, 종료) 또는 단일)
            {
                "특공접수":   ("sptPblancHseRceptBgnde", "sptPblancHseRceptEndde"),
                "일반접수":   ("rceptBgnde", "rceptEndde"),
                "계약":       ("cntrctBgnde", "cntrctEndde"),
            },
            "przwinPblancDe",   # 당첨자 발표일
        ),
        "무순위/잔여": (
            f"https://apis.data.go.kr/B551011/APTLttotPblancSvc/"
            f"getRemndrMstList?serviceKey={KEY}&{common_params}",
            {
                "무순위접수": ("subscrptRceptBgnde", "subscrptRceptEndde"),
                "계약":       ("cntrctBgnde", "cntrctEndde"),
            },
            "przwinPblancDe",
        ),
    }

    today_list    = []
    upcoming_list = []

    for label, (url, date_fields, przwin_field) in endpoints.items():
        print(f"\n🔗 [{label}] 호출 중...")
        items = call_api(url, label)
        print(f"  수집: {len(items)}건")

        for item in items:
            name = (item.get("houseNm") or item.get("houseName") or "").strip()
            area = (item.get("hssplyAdres") or "").strip()
            if not name:
                continue

            today_tags    = []
            upcoming_tags = []

            for tag, (sf, ef) in date_fields.items():
                s, e = sd(item.get(sf)), sd(item.get(ef))
                if in_range(s, e, today_int):
                    today_tags.append(tag)
                elif s and not in_range(s, e, today_int):
                    try:
                        si = int(s)
                        if today_int < si <= week_later:
                            upcoming_tags.append(f"{tag}(~{s[4:6]}/{s[6:]}시작)")
                    except ValueError:
                        pass

            pdate = sd(item.get(przwin_field))
            if exact(pdate, today_int):
                today_tags.append("당첨자발표")
            elif pdate:
                try:
                    pi = int(pdate)
                    if today_int < pi <= week_later:
                        upcoming_tags.append(f"당첨자발표({pdate[4:6]}/{pdate[6:]})")
                except ValueError:
                    pass

            if today_tags:
                today_list.append(f"[{'·'.join(today_tags)}] {name} ({area})")
            if upcoming_tags:
                upcoming_list.append(f"[{'·'.join(upcoming_tags)}] {name} ({area})")

    today_list    = sorted(set(today_list))
    upcoming_list = sorted(set(upcoming_list))
    print(f"\n🎯 오늘 {len(today_list)}건 / 향후7일 {len(upcoming_list)}건")
    return {"today": today_list, "upcoming": upcoming_list, "errors": []}


# ── 이메일 ────────────────────────────────────────────────

def item_list_html(items: list, dot_color: str) -> str:
    if not items:
        return "<p style='color:#999;text-align:center;padding:12px;'>해당 없음</p>"
    rows = "".join(
        f"<li style='padding:8px 0;border-bottom:1px dashed #ddd;font-size:14px;color:#222;'>"
        f"<span style='color:{dot_color};font-weight:bold;'>●</span> {it}</li>"
        for it in items
    )
    return f"<ul style='list-style:none;padding:0;margin:0;'>{rows}</ul>"


def build_html(today: list, upcoming: list) -> str:
    ds = datetime.now().strftime("%Y-%m-%d")
    return f"""<html><body style="font-family:'Malgun Gothic',sans-serif;max-width:720px;margin:0 auto;color:#333;">
<h2 style="color:#0056b3;border-bottom:3px solid #0056b3;padding-bottom:8px;">
🏠 청약Home 오늘의 아파트 공급 정보</h2>
<p><strong>{ds}</strong> 기준 청약 일정 알림입니다.</p>

<h3 style="color:#0056b3;margin-top:20px;">📌 오늘 진행 중인 청약 ({len(today)}건)</h3>
<div style="background:#f0f4ff;padding:16px;border-radius:6px;border:1px solid #c5d3f0;">
{item_list_html(today, "#0056b3")}</div>

<h3 style="color:#b84c00;margin-top:20px;">📅 향후 7일 내 시작 예정 ({len(upcoming)}건)</h3>
<div style="background:#fff8f0;padding:16px;border-radius:6px;border:1px solid #e8c98a;">
{item_list_html(upcoming, "#b84c00")}</div>

<p style="font-size:11px;color:#aaa;margin-top:24px;border-top:1px solid #eee;padding-top:8px;">
※ 공공데이터포털 한국부동산원 청약홈 API (APTLttotPblancSvc) 기반 자동 발송<br>
※ 실제 일정은 <a href="https://www.applyhome.co.kr">applyhome.co.kr</a>에서 반드시 확인하세요.
</p></body></html>"""


def send_email(result: dict):
    today_list    = result.get("today", [])
    upcoming_list = result.get("upcoming", [])
    errors        = result.get("errors", [])
    ds            = datetime.now().strftime("%Y-%m-%d")

    if errors:
        html    = f"<p style='color:red;font-weight:bold;'>{errors[0]}</p>"
        subject = f"🔔 [청약알림] {ds} - ⚠️ 오류 발생"
    else:
        html    = build_html(today_list, upcoming_list)
        subject = f"🔔 [청약알림] {ds} - 오늘 {len(today_list)}건 / 7일내 {len(upcoming_list)}건"

    msg            = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECEIVER_EMAIL
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as srv:
            srv.ehlo(); srv.starttls(); srv.ehlo()
            srv.login(SENDER_EMAIL, SENDER_PASSWORD)
            srv.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print(f"📧 발송 성공! 제목: {subject}")
    except Exception as e:
        print(f"❌ 발송 실패: {e}")
        raise


if __name__ == "__main__":
    result = get_subscription_data()
    send_email(result)
