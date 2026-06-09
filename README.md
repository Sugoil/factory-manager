<<<<<<< HEAD
# 전체 부동산 매물 관리

공장, 창고, 토지, 상가, 원룸, 투룸, 쓰리룸, 아파트, 빌라, 오피스텔,
사무실 등 모든 부동산 매물을 관리하는 비밀번호 보호 Streamlit 앱입니다.

## 주요 기능

- `st.secrets` 비밀번호 로그인
- 매물종류와 거래유형별 관리
- 매물종류에 맞는 추가 입력 항목 표시
- 사진 및 네이버부동산 링크 저장
- 네이버부동산 URL에서 공개된 매물 정보 자동 추출 시도
- 평수, 평당가, 월세 수익률, 전세가율, 보증금 비율 자동 계산
- 종류·지역·거래유형·가격·월세·키워드 필터
- 수익률, 평당가, 매매가 정렬
- CSV 저장, 불러오기, 다운로드

네이버부동산 페이지 구조나 접근 정책에 따라 자동 추출이 되지 않을 수 있습니다.
이 경우 앱은 오류 없이 `자동 추출 실패, 직접 입력해주세요`라고 안내합니다.

## 자동 계산 기준

- 평수: `면적(㎡) ÷ 3.3058`
- 평당가: 매물종류에 따라 대지·전용·건물면적 중 적절한 면적 사용
- 월세 수익률: `월세 × 12 ÷ (매매가 - 보증금) × 100`
- 전세가율: 전세 매물의 `보증금 ÷ 매매가 × 100`
- 매매가 대비 보증금 비율: `보증금 ÷ 매매가 × 100`
- 공장·창고 건폐율: `건축면적 ÷ 대지면적 × 100`
- 공장·창고 용적률: `건물면적 ÷ 대지면적 × 100`

## 내 컴퓨터에서 실행

### 1. 패키지 설치

=======
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

>>>>>>> 6b61f5762b97e3c22446bf2ee6f478d968926922
```powershell
cd "C:\Users\skte3\Documents\부동산"
python -m pip install -r requirements.txt
```

<<<<<<< HEAD
### 2. 비밀번호 설정

`.streamlit/secrets.toml` 파일을 만들고 다음 내용을 입력합니다.
=======
### 2. 로그인 비밀번호 설정

`.streamlit` 폴더 안에 `secrets.toml` 파일을 만듭니다.

```text
C:\Users\skte3\Documents\부동산\.streamlit\secrets.toml
```

파일 내용:
>>>>>>> 6b61f5762b97e3c22446bf2ee6f478d968926922

```toml
APP_PASSWORD = "내가-사용할-비밀번호"
```

<<<<<<< HEAD
실제 `secrets.toml` 파일은 GitHub에 올리지 마세요.
=======
`.streamlit/secrets.toml.example` 파일을 복사하여 사용할 수도 있습니다.
실제 `secrets.toml` 파일은 GitHub에 올리면 안 됩니다. `.gitignore`가 해당
파일의 업로드를 막도록 설정되어 있습니다.
>>>>>>> 6b61f5762b97e3c22446bf2ee6f478d968926922

### 3. 앱 실행

```powershell
cd "C:\Users\skte3\Documents\부동산"
python -m streamlit run app.py
```

<<<<<<< HEAD
## Streamlit Community Cloud 배포

1. GitHub 저장소에 `app.py`, `requirements.txt`, `README.md`, `.gitignore`,
   `listings.csv`를 업로드합니다.
2. 실제 `.streamlit/secrets.toml` 파일은 업로드하지 않습니다.
3. [Streamlit Community Cloud](https://share.streamlit.io/)에서 저장소를
   선택하고 Main file path를 `app.py`로 설정합니다.
4. `Advanced settings → Secrets`에 다음 내용을 입력합니다.
=======
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
>>>>>>> 6b61f5762b97e3c22446bf2ee6f478d968926922

```toml
APP_PASSWORD = "휴대폰에서-사용할-비밀번호"
```

<<<<<<< HEAD
5. `Deploy`를 누릅니다.

Cloud 내부 CSV는 영구 저장소가 아닙니다. 사용 후 반드시 전체 CSV를 다운로드해
백업하고, 다음 사용 시 CSV 불러오기 기능으로 복원하세요.

## 매일 오전 9시 네이버 매물 확인

`.github/workflows/daily-naver-watch.yml`은 매일 오전 9시(KST)에 실행됩니다.
과도한 요청을 막기 위해 검색 URL은 최대 5개, 상세 매물은 최대 10개만 확인하며
각 요청 사이에 최소 6초를 기다립니다.

GitHub 저장소의 `Settings → Secrets and variables → Actions`에서 설정합니다.
자동 CSV 커밋 권한이 거부되면 `Settings → Actions → General → Workflow
permissions`에서 `Read and write permissions`를 선택합니다.

### Repository secret

`NAVER_WATCH_URLS`에 직접 만든 네이버부동산 검색 결과 URL 또는 매물 URL을
줄바꿈으로 구분하여 입력합니다.

### Repository variables

필요한 조건만 설정하고, 사용하지 않는 조건은 빈 값으로 둡니다.

```text
WATCH_REGIONS=경기도 화성시,경기도 평택시
WATCH_PROPERTY_TYPES=공장,창고
WATCH_DEAL_TYPES=매매
WATCH_MIN_PRICE=0
WATCH_MAX_PRICE=150000
WATCH_MIN_RENT=0
WATCH_MAX_RENT=0
```

신규 매물은 네이버부동산 링크를 기준으로 중복을 제거한 후 `listings.csv`에
추가됩니다. 자동 추출 실패나 접근 제한은 앱을 중단시키지 않고
`logs/naver_collector.log`에 기록됩니다.

네이버부동산 페이지 구조나 접근 정책이 변경되면 자동 수집이 작동하지 않을 수
있습니다. 공개 페이지를 소규모로만 확인하고, 수집 간격과 최대 요청 수를 늘리지
않는 것을 권장합니다.

## GitHub 자동 반영

PowerShell에서 아래 명령을 실행하면 수정 파일을 자동으로 add, commit, push합니다.

```powershell
cd "C:\Users\skte3\Documents\부동산"
powershell -ExecutionPolicy Bypass -File .\sync-github.ps1 -Message "업데이트 내용"
```

연결 저장소:

```text
https://github.com/Sugoil/factory-manager
```

실제 비밀번호가 저장된 `.streamlit/secrets.toml`은 업로드되지 않습니다.
=======
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
>>>>>>> 6b61f5762b97e3c22446bf2ee6f478d968926922
