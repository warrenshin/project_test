"""배포된 인스턴스(로컬 uvicorn이든 docker-compose든)에 대해 핵심 흐름이
살아있는지 확인하는 smoke test.

    python -m scripts.smoke_test
    python -m scripts.smoke_test --base-url http://localhost:8000 --origin http://localhost:3000

몇 번을 실행해도 안전하다 — 매번 새 무작위 이메일로 회원가입하므로 기존
사용자·일지·포트폴리오 데이터를 건드리거나 훼손하지 않는다. 어느 단계든
실패하면 그 자리에서 멈추고(무한 재시도 없음) 0이 아닌 코드로 종료한다.

CSRF Origin 검증 미들웨어(app/core/csrf.py) 때문에 상태변경 요청에는 항상
허용된 Origin 헤더가 실려야 한다 — --origin 기본값은 CORS_ALLOWED_ORIGINS_RAW
기본값과 맞춰 두었다.
"""

import argparse
import sys
import uuid

import httpx


def _step(name: str) -> None:
    print(f"[smoke] {name} ...", end=" ", flush=True)


def _ok() -> None:
    print("OK")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--origin", default="http://localhost:3000")
    args = parser.parse_args()

    run_id = uuid.uuid4().hex[:12]
    email = f"smoke-{run_id}@example.com"
    password = "smoke-test-passphrase-1"

    try:
        with httpx.Client(base_url=args.base_url, headers={"Origin": args.origin}, timeout=10.0) as client:
            _step("liveness (/health/live)")
            r = client.get("/health/live")
            assert r.status_code == 200, f"unexpected status {r.status_code}: {r.text}"
            _ok()

            _step("readiness (/health/ready)")
            r = client.get("/health/ready")
            assert r.status_code == 200, f"unexpected status {r.status_code}: {r.text}"
            _ok()

            _step(f"회원가입 ({email})")
            r = client.post(
                "/v1/auth/signup",
                json={
                    "email": email,
                    "password": password,
                    "birth_date": "2000-01-01",
                    "consents": [
                        {"consent_type": "TERMS", "version": "v1", "agreed": True},
                        {"consent_type": "PRIVACY", "version": "v1", "agreed": True},
                        {"consent_type": "MARKETING", "version": "v1", "agreed": False},
                    ],
                },
            )
            assert r.status_code in (200, 201), f"unexpected status {r.status_code}: {r.text}"
            assert "token" not in r.text.lower(), "회원가입 응답 본문에 토큰으로 보이는 값이 있다"
            _ok()

            _step("로그아웃 (재로그인 흐름 검증을 위해)")
            r = client.post("/v1/auth/logout")
            assert r.status_code == 204, f"unexpected status {r.status_code}: {r.text}"
            _ok()

            _step("로그인 및 쿠키 설정 확인")
            r = client.post("/v1/auth/login", json={"email": email, "password": password})
            assert r.status_code == 200, f"unexpected status {r.status_code}: {r.text}"
            assert "token" not in r.text.lower(), "로그인 응답 본문에 토큰으로 보이는 값이 있다"
            set_cookie_headers = r.headers.get_list("set-cookie")
            assert any("httponly" in h.lower() for h in set_cookie_headers), "Set-Cookie에 HttpOnly가 없다"
            _ok()

            _step("/v1/auth/me (로그인 상태 확인)")
            r = client.get("/v1/auth/me")
            assert r.status_code == 200, f"unexpected status {r.status_code}: {r.text}"
            assert r.json()["email"] == email
            _ok()

            _step("1강 조회")
            r = client.get("/v1/learning/paths")
            assert r.status_code == 200, f"unexpected status {r.status_code}: {r.text}"
            paths = r.json()
            lesson = paths[0]["courses"][0]["modules"][0]["lessons"][0]
            lesson_id = lesson["id"]
            r = client.get(f"/v1/lessons/{lesson_id}")
            assert r.status_code == 200, f"unexpected status {r.status_code}: {r.text}"
            lesson_detail = r.json()
            _ok()

            _step("퀴즈 제출")
            r = client.post(f"/v1/lessons/{lesson_id}/progress", json={"status": "COMPLETED"})
            assert r.status_code == 200, f"unexpected status {r.status_code}: {r.text}"
            quiz_id = lesson_detail["quiz"]["id"]
            r = client.get(f"/v1/quizzes/{quiz_id}")
            assert r.status_code == 200, f"unexpected status {r.status_code}: {r.text}"
            quiz = r.json()
            answers = {q["id"]: [q["choices"][0]["id"]] for q in quiz["questions"]}
            r = client.post(f"/v1/quizzes/{quiz_id}/attempts", json={"answers": answers})
            assert r.status_code == 200, f"unexpected status {r.status_code}: {r.text}"
            _ok()

            _step("SK하이닉스 검색")
            r = client.get("/v1/instruments/search", params={"q": "SK하이닉스"})
            assert r.status_code == 200, f"unexpected status {r.status_code}: {r.text}"
            instruments = r.json()
            assert instruments, "SK하이닉스 검색 결과가 비어 있다"
            instrument_id = instruments[0]["id"]
            _ok()

            _step("포트폴리오 확인")
            r = client.get("/v1/me/portfolio")
            assert r.status_code == 200, f"unexpected status {r.status_code}: {r.text}"
            portfolio_id = r.json()["id"]
            _ok()

            _step("거래 전 투자일지 생성")
            r = client.post(
                "/v1/journals/pre-trade",
                json={
                    "portfolio_id": portfolio_id,
                    "instrument_id": instrument_id,
                    "thesis": "smoke test용 임시 논리",
                    "supporting_evidence": ["smoke test"],
                    "counter_evidence": ["smoke test"],
                    "planned_weight_pct": "5",
                },
            )
            assert r.status_code in (200, 201), f"unexpected status {r.status_code}: {r.text}"
            journal_id = r.json()["id"]
            _ok()

            _step("가상 시장가 매수 주문")
            r = client.post(
                f"/v1/portfolios/{portfolio_id}/orders",
                json={
                    "instrument_id": instrument_id,
                    "side": "BUY",
                    "order_type": "MARKET",
                    "quantity": "1",
                    "pre_trade_journal_id": journal_id,
                },
                headers={"Idempotency-Key": f"smoke-{run_id}"},
            )
            assert r.status_code in (200, 201), f"unexpected status {r.status_code}: {r.text}"
            _ok()

            _step("포트폴리오 반영 확인")
            r = client.get(f"/v1/portfolios/{portfolio_id}/positions")
            assert r.status_code == 200, f"unexpected status {r.status_code}: {r.text}"
            tickers = [p["ticker"] for p in r.json()]
            assert instruments[0]["ticker"] in tickers, "매수한 종목이 포지션에 반영되지 않았다"
            _ok()

            _step("로그아웃")
            r = client.post("/v1/auth/logout")
            assert r.status_code == 204, f"unexpected status {r.status_code}: {r.text}"
            _ok()

            _step("로그아웃 후 보호 API 401 확인")
            r = client.get("/v1/me/portfolio")
            assert r.status_code == 401, f"unexpected status {r.status_code}: {r.text}"
            _ok()

    except AssertionError as exc:
        print("FAILED")
        print(f"[smoke] 실패: {exc}", file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        print("FAILED")
        print(f"[smoke] 네트워크 오류: {exc}", file=sys.stderr)
        return 1

    print(f"[smoke] 모든 단계 통과 (계정: {email})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
