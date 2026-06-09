# 전체 부동산 매물 관리

공장, 창고, 토지, 상가, 원룸, 투룸, 쓰리룸, 아파트, 빌라, 오피스텔,
사무실 등 모든 부동산 매물을 관리하는 비밀번호 보호 Streamlit 앱입니다.

## 주요 기능

- `st.secrets` 비밀번호 로그인
- 매물종류와 거래유형별 관리
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

```powershell
cd "C:\Users\skte3\Documents\부동산"
python -m pip install -r requirements.txt
```

### 2. 비밀번호 설정

`.streamlit/secrets.toml` 파일을 만들고 다음 내용을 입력합니다.

```toml
APP_PASSWORD = "내가-사용할-비밀번호"
```

실제 `secrets.toml` 파일은 GitHub에 올리지 마세요.

### 3. 앱 실행

```powershell
cd "C:\Users\skte3\Documents\부동산"
python -m streamlit run app.py
```

## Streamlit Community Cloud 배포

1. GitHub 저장소에 프로젝트 파일을 업로드합니다.
2. 실제 `.streamlit/secrets.toml` 파일은 업로드하지 않습니다.
3. Streamlit Community Cloud에서 저장소를 선택합니다.
4. Main file path를 `app.py`로 설정합니다.
5. `Advanced settings → Secrets`에 비밀번호를 입력합니다.

```toml
APP_PASSWORD = "휴대폰에서-사용할-비밀번호"
```

6. `Deploy`를 누릅니다.

Cloud 내부 CSV는 영구 저장소가 아닙니다. 사용 후 반드시 전체 CSV를 다운로드해
백업하고, 다음 사용 시 CSV 불러오기 기능으로 복원하세요.

## 매일 오전 9시 네이버 매물 확인

`.github/workflows/daily-naver-watch.yml`은 매일 오전 9시(KST)에 실행됩니다.
검색 URL은 최대 5개, 상세 매물은 최대 10개만 확인하며 각 요청 사이에 최소
6초를 기다립니다.

GitHub 저장소의 `Settings → Secrets and variables → Actions`에서 설정합니다.
자동 CSV 커밋 권한이 거부되면 `Settings → Actions → General → Workflow
permissions`에서 `Read and write permissions`를 선택합니다.

### Repository secret

`NAVER_WATCH_URLS`에 직접 만든 네이버부동산 검색 결과 URL 또는 매물 URL을
줄바꿈으로 구분하여 입력합니다.

### Repository variables

```text
WATCH_REGIONS=경기도 화성시,경기도 평택시
WATCH_PROPERTY_TYPES=공장,창고
WATCH_DEAL_TYPES=매매
WATCH_MIN_PRICE=0
WATCH_MAX_PRICE=150000
WATCH_MIN_RENT=0
WATCH_MAX_RENT=0
```

신규 매물은 네이버부동산 매물 ID를 기준으로 중복을 제거한 후 `listings.csv`에
추가됩니다. 자동 추출 실패나 접근 제한은 앱을 중단시키지 않고 실행 로그
아티팩트에 기록됩니다.

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

자동 GitHub 반영 테스트 완료
