# 주식 포트폴리오 모바일 앱 (Streamlit Cloud 배포용)

기존 `web_app.py`는 그대로 두고, 클라우드에 올려서 노트북 없이 폰에서 단독으로 쓸 수 있도록
이 폴더(`mobile_app/`)에 동일한 앱을 옮겨왔습니다. 모바일 화면에 맞춰 요약 카드 배치만 2x2로 조정했습니다.

## 배포 방법 (1회만 설정, 무료)

1. 이 변경사항을 GitHub(`warrenshin/project_test`)에 push 합니다.
   ```
   git add mobile_app
   git commit -m "Add mobile_app for Streamlit Cloud deployment"
   git push
   ```
2. https://share.streamlit.io 접속 후 GitHub 계정으로 로그인합니다.
3. "New app" → Repository: `warrenshin/project_test`, Branch: `main`(또는 사용 중인 브랜치),
   Main file path: `mobile_app/app.py` 를 선택하고 Deploy 클릭.
4. 몇 분 후 `https://<임의이름>.streamlit.app` 같은 주소가 발급됩니다. 이 주소는 노트북을 꺼도
   항상 동작합니다(서버가 Streamlit Cloud에서 실행되기 때문).

## 폰에서 앱처럼 쓰기

1. 폰 브라우저(크롬/사파리)에서 위 주소로 접속합니다.
2. 크롬: 메뉴(⋮) → "홈 화면에 추가" / 사파리: 공유 버튼 → "홈 화면에 추가" 선택합니다.
3. 홈 화면에 아이콘이 생기고, 탭하면 주소창 없이 앱처럼 전체화면으로 실행됩니다.

## 데이터 업데이트 주기

- 구글 스프레드시트 데이터는 5분(`ttl=300`) 캐시, 뉴스는 10분(`ttl=600`) 캐시입니다.
- 화면의 "🔄 데이터 새로고침" 버튼으로 즉시 갱신할 수 있습니다.

## 참고

- Streamlit Cloud 앱은 일정 시간 미사용 시 절전(sleep) 상태가 될 수 있고, 다시 접속하면 자동으로
  깨어나며 로딩에 몇 초~수십 초 걸릴 수 있습니다.
- 더 빠른 응답이나 완전한 네이티브 앱(앱스토어 설치형)이 필요하면 별도 요청해주세요.
