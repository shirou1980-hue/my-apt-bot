import urllib.request
import json
import ssl

def scan_swagger():
    print("==================================================")
    print("🔍 [최종 진단] 공공데이터포털 서버 설계도(Swagger) 스캔")
    print("==================================================")

    # 선생님께서 올려주신 두 가지 서비스의 설계도 원본 주소
    urls = {
        "[후보 1] 분양정보 조회 서비스": "https://infuser.odcloud.kr/api/stages/37000/api-docs",
        "[후보 2] APT 분양정보": "https://infuser.odcloud.kr/oas/docs?namespace=15101046/v1"
    }

    # 보안 인증 무시 처리 (정부망 SSL 오류 우회)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    headers = {'User-Agent': 'Mozilla/5.0'}

    for name, url in urls.items():
        print(f"\n▶ {name} 탐색 중...")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                
                # Base URL 확인
                servers = data.get('servers', [])
                if servers:
                    print(f" - 서버 기본 주소: {servers[0].get('url', 'N/A')}")
                else:
                    print(f" - 서버 기본 주소: {data.get('basePath', 'N/A')}")
                
                # 세부 경로(방 번호) 추출
                paths = data.get('paths', {})
                if not paths:
                    print(" - ⚠️ 찾을 수 없음")
                else:
                    for p in paths.keys():
                        print(f" ✅ 발견된 데이터 진짜 주소: {p}")
        except Exception as e:
            print(f" ❌ 접근 실패: {e}")

    print("\n==================================================")
    print("스캔 완료! 위 로그 화면을 복사해서 알려주세요!")
    print("==================================================")

if __name__ == "__main__":
    scan_swagger()
