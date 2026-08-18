"""컨테이너 재시작 후에도 사용자 데이터가 유지되는지 확인하는 2단계 스크립트.

운영 데이터를 조회만 할 뿐, 삭제하거나 변형하는 기능은 전혀 없다. 매번 새
무작위 이메일로 가입하므로 기존 데이터를 건드리지 않는다.

    # 1) 컨테이너를 재시작하기 전에 실행 — 테스트 사용자와 식별 가능한
    #    투자일지를 만들고, 로그인 정보(이메일/비밀번호 — 토큰 아님)를
    #    state 파일에 저장한다.
    python -m scripts.restart_persistence_test --phase setup \
        --state-file /tmp/restart-persistence-state.json \
        --base-url http://localhost:8000 --origin http://localhost:3000

    # (여기서 web/api/postgres 컨테이너를 재시작하고 health가 다시 정상화될
    #  때까지 기다린다)

    # 2) 재시작 후 실행 — state 파일의 계정으로 다시 로그인해 데이터가 그대로
    #    있는지 확인한다. 성공하면 state 파일을 스스로 삭제한다.
    python -m scripts.restart_persistence_test --phase verify \
        --state-file /tmp/restart-persistence-state.json \
        --base-url http://localhost:8000 --origin http://localhost:3000

state 파일에는 이메일·비밀번호(이번 실행 전용 임시 계정)와 식별용 문자열만
저장한다 — 토큰은 어디에도 기록하지 않는다. 비밀번호나 쿠키 값은 표준출력에
절대 찍지 않는다.
"""

import argparse
import json
import sys
import uuid
from pathlib import Path

import httpx


def _step(name: str) -> None:
    print(f"[persistence] {name} ...", end=" ", flush=True)


def _ok() -> None:
    print("OK")


def run_setup(client: httpx.Client, state_path: Path) -> int:
    run_id = uuid.uuid4().hex[:12]
    email = f"restart-persistence-{run_id}@example.com"
    password = f"pw-{uuid.uuid4().hex[:16]}"
    marker = f"restart-persistence-marker-{run_id}"

    try:
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
        _ok()

        _step("식별 가능한 투자일지 생성 (구분용 마커 포함)")
        r = client.get("/v1/instruments/search", params={"q": "삼성전자"})
        assert r.status_code == 200, f"unexpected status {r.status_code}: {r.text}"
        instruments = r.json()
        assert instruments, "삼성전자 검색 결과가 비어 있다"
        instrument_id = instruments[0]["id"]

        r = client.get("/v1/me/portfolio")
        assert r.status_code == 200, f"unexpected status {r.status_code}: {r.text}"
        portfolio_id = r.json()["id"]

        r = client.post(
            "/v1/journals/pre-trade",
            json={
                "portfolio_id": portfolio_id,
                "instrument_id": instrument_id,
                "thesis": marker,
                "supporting_evidence": ["restart persistence test"],
                "counter_evidence": ["restart persistence test"],
                "planned_weight_pct": "5",
            },
        )
        assert r.status_code in (200, 201), f"unexpected status {r.status_code}: {r.text}"
        journal_id = r.json()["id"]
        _ok()

    except AssertionError as exc:
        print("FAILED")
        print(f"[persistence] setup 실패: {exc}", file=sys.stderr)
        return 1

    state_path.write_text(
        json.dumps({"email": email, "password": password, "marker": marker, "journal_id": journal_id})
    )
    print(f"[persistence] setup 완료 — state 파일에 저장됨 (계정: {email}, 비밀번호/토큰은 출력하지 않음)")
    return 0


def run_verify(client: httpx.Client, state_path: Path) -> int:
    if not state_path.exists():
        print(f"[persistence] state 파일이 없다: {state_path}", file=sys.stderr)
        return 1
    state = json.loads(state_path.read_text())

    try:
        _step("재시작 후 동일 계정으로 재로그인")
        r = client.post("/v1/auth/login", json={"email": state["email"], "password": state["password"]})
        assert r.status_code == 200, f"unexpected status {r.status_code}: {r.text}"
        _ok()

        _step("재시작 전 생성한 투자일지가 그대로 존재하는지 확인")
        r = client.get(f"/v1/journals/{state['journal_id']}")
        assert r.status_code == 200, f"unexpected status {r.status_code}: {r.text}"
        assert r.json()["thesis"] == state["marker"], "재시작 후 투자일지 내용이 재시작 전과 다르다"
        _ok()

        _step("로그아웃")
        r = client.post("/v1/auth/logout")
        assert r.status_code == 204, f"unexpected status {r.status_code}: {r.text}"
        _ok()

    except AssertionError as exc:
        print("FAILED")
        print(f"[persistence] verify 실패: {exc}", file=sys.stderr)
        return 1
    except KeyError as exc:
        print("FAILED")
        print(f"[persistence] state 파일 형식이 잘못됐다: {exc}", file=sys.stderr)
        return 1

    state_path.unlink(missing_ok=True)
    print("[persistence] verify 완료 — 재시작 후에도 데이터가 유지됐다. state 파일을 정리했다.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=["setup", "verify"])
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--origin", default="http://localhost:3000")
    args = parser.parse_args()

    state_path = Path(args.state_file)

    try:
        with httpx.Client(base_url=args.base_url, headers={"Origin": args.origin}, timeout=10.0) as client:
            if args.phase == "setup":
                return run_setup(client, state_path)
            return run_verify(client, state_path)
    except httpx.HTTPError as exc:
        print("FAILED")
        print(f"[persistence] 네트워크 오류: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
