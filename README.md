# 개인용 부동산 매물 관리

공장, 토지, 상가, 원룸 매물을 관리하는 비밀번호 보호 Streamlit 앱입니다.
컴퓨터에서 실행하거나 Streamlit Community Cloud에 배포하여 휴대폰에서 사용할
수 있습니다.

## 기능

- `st.secrets`를 사용하는 비밀번호 로그인
- 로그인 성공 후에만 매물 관리 화면 표시
- 공장 / 토지 / 상가 / 원룸 분류 탭
- 대지·건물 평수와 평당가 자동 계산
- 월세 수익률 자동 계산
- 지역 검색, 매물 검색, 지역 필터, 가격·수익률 정렬
- 공장 기반시설 기록 및 투자 의견 자동 생성
- CSV 불러오기, 로컬 저장, 목록 다운로드

## 내 컴퓨터에서 실행하기

### 1. 패키지 설치

PowerShell에서 다음 명령을 실행합니다.

```powershell
cd "C:\Users\skte3\Documents\부동산"
python -m pip install -r requirements.txt
```

### 2. 로그인 비밀번호 설정

`.streamlit` 폴더 안에 `secrets.toml` 파일을 만듭니다.

```text
C:\Users\skte3\Documents\부동산\.streamlit\secrets.toml
```

파일 내용:

```toml
APP_PASSWORD = "내가-사용할-비밀번호"
```

`.streamlit/secrets.toml.example` 파일을 복사하여 사용할 수도 있습니다.
실제 `secrets.toml` 파일은 GitHub에 올리면 안 됩니다. `.gitignore`가 해당
파일의 업로드를 막도록 설정되어 있습니다.

### 3. 앱 실행

```powershell
cd "C:\Users\skte3\Documents\부동산"
python -m streamlit run app.py
```

브라우저에서 비밀번호를 입력하면 매물 관리 화면이 열립니다.

## 휴대폰 사용을 위한 Community Cloud 배포

### 1. GitHub 저장소 준비

1. [GitHub](https://github.com)에 로그인합니다.
2. 오른쪽 위 `+` 버튼에서 `New repository`를 선택합니다.
3. 저장소 이름을 입력합니다.
4. 개인 자료 보호를 위해 가능하면 `Private` 저장소를 선택합니다.
5. 다음 파일을 저장소에 업로드합니다.

```text
app.py
requirements.txt
README.md
.gitignore
.streamlit/secrets.toml.example
listings.csv
```

실제 비밀번호가 들어간 `.streamlit/secrets.toml`은 업로드하지 마세요.

### 2. Streamlit Community Cloud에 배포

1. [Streamlit Community Cloud](https://share.streamlit.io/)에 GitHub 계정으로
   로그인합니다.
2. `Create app`을 누릅니다.
3. 업로드한 GitHub 저장소와 브랜치를 선택합니다.
4. Main file path에 `app.py`를 입력합니다.
5. `Advanced settings`를 열고 Secrets 입력란에 아래 내용을 넣습니다.

```toml
APP_PASSWORD = "휴대폰에서-사용할-비밀번호"
```

6. `Deploy`를 누릅니다.
7. 배포가 완료되면 생성된 주소를 휴대폰 브라우저에서 엽니다.
8. 설정한 비밀번호로 로그인합니다.

비밀번호를 변경하려면 Community Cloud 앱 설정의 `Secrets`에서
`APP_PASSWORD`를 수정합니다.

## 사용 방법

1. 비밀번호로 로그인합니다.
2. `새 매물 등록`에서 매물 종류와 정보를 입력합니다.
3. 면적은 ㎡ 단위, 금액은 만원 단위로 입력합니다.
4. 저장하면 평수, 평당가, 수익률이 자동 계산됩니다.
5. 아래 검색 영역과 종류별 탭에서 매물을 확인합니다.
6. 사용 후 `전체 CSV 다운로드`로 최신 데이터를 백업합니다.

## Cloud CSV 저장 주의사항

컴퓨터에서 실행할 때는 입력한 매물이 `listings.csv`에 저장됩니다.

Streamlit Community Cloud의 앱 내부 파일은 영구 저장소가 아닙니다. 앱이
재시작되거나 다시 배포되면 Cloud에서 새로 입력한 데이터가 사라질 수 있습니다.
휴대폰에서 사용한 뒤에는 반드시 전체 CSV를 다운로드하세요. 다음 접속 시
다운로드한 CSV를 앱에서 다시 불러올 수 있습니다.

## 계산 기준

- 평수: `면적(㎡) ÷ 3.3058`
- 평당가: `매매가 ÷ 면적(평)`
- 월세 수익률: `월세 × 12 ÷ (매매가 - 보증금) × 100`
