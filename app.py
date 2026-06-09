import hmac
from pathlib import Path

import pandas as pd
import streamlit as st


DATA_FILE = Path(__file__).with_name("listings.csv")
PYEONG = 3.3058
PROPERTY_TYPES = ["공장", "토지", "상가", "원룸"]

COLUMNS = [
    "매물명",
    "매물종류",
    "주소",
    "지역",
    "매매가(만원)",
    "보증금(만원)",
    "월세(만원)",
    "대지면적(㎡)",
    "건물면적(㎡)",
    "대지면적(평)",
    "건물면적(평)",
    "토지 평당가(만원)",
    "건물 평당가(만원)",
    "월세 수익률(%)",
    "용도지역",
    "진입도로 폭(m)",
    "상수도",
    "하수도",
    "전력량(kW)",
    "호이스트",
    "폐수 가능 여부",
    "공장등록 가능 여부",
    "대형차 진입 가능 여부",
    "분석점수",
    "투자의견",
    "메모",
]

NUMBER_COLUMNS = [
    "매매가(만원)",
    "보증금(만원)",
    "월세(만원)",
    "대지면적(㎡)",
    "건물면적(㎡)",
    "진입도로 폭(m)",
    "전력량(kW)",
]

FACTORY_SELECT_COLUMNS = [
    "상수도",
    "하수도",
    "호이스트",
    "폐수 가능 여부",
    "공장등록 가능 여부",
    "대형차 진입 가능 여부",
]


def get_region(address):
    address = str(address).strip()
    return address.split()[0] if address else "지역 미입력"


def read_csv_file(file):
    last_error = None
    for encoding in ["utf-8-sig", "cp949"]:
        try:
            if hasattr(file, "seek"):
                file.seek(0)
            return pd.read_csv(file, encoding=encoding)
        except UnicodeDecodeError as error:
            last_error = error
    raise last_error


def factory_score(row):
    score = 0
    strengths = []
    cautions = []
    road_width = row["진입도로 폭(m)"]
    power = row["전력량(kW)"]

    if road_width >= 8:
        score += 20
        strengths.append("물류 차량 운행에 유리한 진입도로")
    elif road_width >= 6:
        score += 14
        strengths.append("무난한 진입도로")
    elif road_width > 0:
        score += 5
        cautions.append("차량 교행과 회전 공간 확인")
    else:
        cautions.append("진입도로 폭 확인")

    checks = [
        ("대형차 진입 가능 여부", "가능", 15, "대형차 진입 가능", "대형차 진입 확인"),
        ("공장등록 가능 여부", "가능", 20, "공장등록 가능", "공장등록 가능 업종 확인"),
        ("상수도", "있음", 8, "상수도 공급", "상수도 공급 확인"),
        ("하수도", "있음", 8, "하수도 사용", "하수 처리 방안 확인"),
        ("호이스트", "있음", 6, "호이스트 설치", ""),
        ("폐수 가능 여부", "가능", 8, "폐수 업종 검토 가능", ""),
    ]
    for column, positive, points, strength, caution in checks:
        if row[column] == positive:
            score += points
            strengths.append(strength)
        elif caution:
            cautions.append(caution)

    if power >= 300:
        score += 15
        strengths.append("대용량 전력")
    elif power >= 100:
        score += 10
        strengths.append("일반 제조업 수준 전력")
    elif power > 0:
        score += 4
        cautions.append("전력 증설 비용 확인")
    else:
        cautions.append("사용 가능 전력량 확인")

    if score >= 80:
        grade = "적극 검토"
    elif score >= 60:
        grade = "조건부 검토"
    elif score >= 40:
        grade = "신중 검토"
    else:
        grade = "추가 확인 필요"

    opinion = f"[{grade}]"
    if strengths:
        opinion += " 장점: " + ", ".join(strengths[:3]) + "."
    if cautions:
        opinion += " 확인사항: " + ", ".join(cautions[:3]) + "."
    return score, opinion


def calculate(row):
    sale_price = row["매매가(만원)"]
    deposit = row["보증금(만원)"]
    monthly_rent = row["월세(만원)"]
    land_pyeong = row["대지면적(㎡)"] / PYEONG if row["대지면적(㎡)"] else 0
    building_pyeong = row["건물면적(㎡)"] / PYEONG if row["건물면적(㎡)"] else 0
    investment = sale_price - deposit
    rental_yield = monthly_rent * 12 / investment * 100 if investment > 0 else 0

    if row["매물종류"] == "공장":
        score, opinion = factory_score(row)
    else:
        score = 0
        opinion = "[기본 검토]"

    if monthly_rent > 0 and rental_yield >= 6:
        opinion += f" 월세 수익률 {rental_yield:.2f}%로 수익성이 양호합니다."
    elif monthly_rent > 0 and rental_yield >= 4:
        opinion += f" 월세 수익률 {rental_yield:.2f}%로 보통 수준입니다."
    elif monthly_rent > 0:
        opinion += f" 월세 수익률 {rental_yield:.2f}%로 가격 검토가 필요합니다."
    else:
        opinion += " 임대수익 정보가 없어 입지와 실사용 가치를 확인해야 합니다."

    return {
        "대지면적(평)": round(land_pyeong, 2),
        "건물면적(평)": round(building_pyeong, 2),
        "토지 평당가(만원)": round(sale_price / land_pyeong, 2) if land_pyeong else 0,
        "건물 평당가(만원)": round(sale_price / building_pyeong, 2)
        if building_pyeong
        else 0,
        "월세 수익률(%)": round(rental_yield, 2),
        "분석점수": score,
        "투자의견": opinion,
    }


def prepare_listings(data):
    data = data.copy()
    for column in COLUMNS:
        if column not in data.columns:
            data[column] = 0 if column in NUMBER_COLUMNS else ""

    data["매물종류"] = data["매물종류"].replace("", "공장").fillna("공장")
    for column in NUMBER_COLUMNS:
        data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0)
    for column in FACTORY_SELECT_COLUMNS:
        data[column] = data[column].replace("", "미확인").fillna("미확인")

    rows = []
    for _, source in data.iterrows():
        row = source.to_dict()
        row["지역"] = get_region(row["주소"])
        row.update(calculate(row))
        rows.append(row)
    return pd.DataFrame(rows, columns=COLUMNS) if rows else pd.DataFrame(columns=COLUMNS)


def load_listings():
    if not DATA_FILE.exists():
        return pd.DataFrame(columns=COLUMNS)
    try:
        return prepare_listings(read_csv_file(DATA_FILE))
    except Exception as error:
        st.warning(f"기존 CSV를 읽지 못했습니다: {error}")
        return pd.DataFrame(columns=COLUMNS)


def save_listings(data):
    data.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")


def get_app_password():
    try:
        return str(st.secrets["APP_PASSWORD"])
    except Exception:
        return ""


def show_login():
    st.title("개인용 부동산 매물 관리")
    with st.form("login_form"):
        password = st.text_input("비밀번호", type="password")
        submitted = st.form_submit_button("로그인", use_container_width=True)
    if submitted:
        app_password = get_app_password()
        if not app_password:
            st.error("앱 비밀번호가 설정되지 않았습니다.")
        elif hmac.compare_digest(password, app_password):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다")


def show_table(data, key):
    st.write(f"표시 매물 **{len(data):,}개**")
    st.dataframe(
        data,
        use_container_width=True,
        hide_index=True,
        column_config={
            "분석점수": st.column_config.ProgressColumn(min_value=0, max_value=100),
            "투자의견": st.column_config.TextColumn(width="large"),
        },
    )
    csv_data = data.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "현재 목록 CSV 다운로드",
        csv_data,
        f"부동산_매물목록_{key}.csv",
        "text/csv",
        key=f"download_{key}",
    )


st.set_page_config(page_title="개인용 부동산 매물 관리", layout="wide")
st.markdown(
    """
    <style>
    .block-container {padding-top: 1.8rem; max-width: 1500px;}
    [data-testid="stMetric"] {
        background: #f5f7fa; border: 1px solid #e1e6ed;
        padding: 14px; border-radius: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if not st.session_state.get("authenticated", False):
    show_login()
    st.stop()

with st.sidebar:
    st.success("로그인됨")
    st.caption("Cloud에서는 사용 후 CSV를 다운로드해 백업하세요.")
    if st.button("로그아웃", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

st.title("개인용 부동산 매물 관리")
st.caption("공장·토지·상가·원룸을 기록하고 가격과 수익성을 자동 계산합니다.")

if "listings" not in st.session_state:
    st.session_state.listings = load_listings()

total = len(st.session_state.listings)
average_price = st.session_state.listings["매매가(만원)"].mean() if total else 0
average_yield = st.session_state.listings["월세 수익률(%)"].mean() if total else 0
regions_count = st.session_state.listings["지역"].nunique() if total else 0

m1, m2, m3, m4 = st.columns(4)
m1.metric("전체 매물", f"{total:,}개")
m2.metric("평균 매매가", f"{average_price:,.0f}만원")
m3.metric("평균 월세 수익률", f"{average_yield:.2f}%")
m4.metric("등록 지역", f"{regions_count:,}곳")

with st.expander("CSV 불러오기 / 전체 다운로드"):
    uploaded_file = st.file_uploader("매물 CSV 불러오기", type="csv")
    if uploaded_file is not None and st.button("CSV 적용"):
        try:
            st.session_state.listings = prepare_listings(read_csv_file(uploaded_file))
            save_listings(st.session_state.listings)
            st.success(f"{len(st.session_state.listings):,}개 매물을 불러왔습니다.")
        except Exception as error:
            st.error(f"CSV를 불러오지 못했습니다: {error}")
    all_csv = st.session_state.listings.to_csv(index=False).encode("utf-8-sig")
    st.download_button("전체 CSV 다운로드", all_csv, "부동산_전체매물.csv", "text/csv")

with st.expander("새 매물 등록", expanded=True):
    with st.form("listing_form", clear_on_submit=True):
        basic, area, factory = st.columns(3)
        with basic:
            st.markdown("#### 기본 정보")
            name = st.text_input("매물명 *")
            property_type = st.selectbox("매물종류", PROPERTY_TYPES)
            address = st.text_input("주소", placeholder="예: 경기도 화성시 ...")
            zoning = st.text_input("용도지역")
            sale_price = st.number_input("매매가(만원) *", min_value=0.0, step=1000.0)
            deposit = st.number_input("보증금(만원)", min_value=0.0, step=100.0)
            monthly_rent = st.number_input("월세(만원)", min_value=0.0, step=10.0)
        with area:
            st.markdown("#### 면적·메모")
            land_area = st.number_input("대지면적(㎡)", min_value=0.0, step=1.0)
            building_area = st.number_input("건물면적(㎡)", min_value=0.0, step=1.0)
            memo = st.text_area("메모", height=220)
        with factory:
            st.markdown("#### 공장 추가 정보")
            st.caption("공장 매물이 아니라면 미확인 상태로 두어도 됩니다.")
            road_width = st.number_input("진입도로 폭(m)", min_value=0.0, step=0.5)
            power = st.number_input("전력량(kW)", min_value=0.0, step=10.0)
            water = st.selectbox("상수도", ["미확인", "있음", "없음"])
            sewer = st.selectbox("하수도", ["미확인", "있음", "없음"])
            hoist = st.selectbox("호이스트", ["미확인", "있음", "없음"])
            wastewater = st.selectbox("폐수 가능 여부", ["미확인", "가능", "불가"])
            registration = st.selectbox("공장등록 가능 여부", ["미확인", "가능", "불가"])
            truck = st.selectbox("대형차 진입 가능 여부", ["미확인", "가능", "불가"])
        submitted = st.form_submit_button("매물 저장", use_container_width=True)

if submitted:
    if not name.strip():
        st.error("매물명을 입력하세요.")
    elif sale_price <= 0:
        st.error("매매가를 입력하세요.")
    else:
        row = {
            "매물명": name.strip(),
            "매물종류": property_type,
            "주소": address.strip(),
            "지역": get_region(address),
            "매매가(만원)": sale_price,
            "보증금(만원)": deposit,
            "월세(만원)": monthly_rent,
            "대지면적(㎡)": land_area,
            "건물면적(㎡)": building_area,
            "용도지역": zoning.strip(),
            "진입도로 폭(m)": road_width,
            "전력량(kW)": power,
            "상수도": water,
            "하수도": sewer,
            "호이스트": hoist,
            "폐수 가능 여부": wastewater,
            "공장등록 가능 여부": registration,
            "대형차 진입 가능 여부": truck,
            "메모": memo.strip(),
        }
        row.update(calculate(row))
        st.session_state.listings = pd.concat(
            [st.session_state.listings, pd.DataFrame([row])], ignore_index=True
        ).reindex(columns=COLUMNS)
        save_listings(st.session_state.listings)
        st.success("매물을 저장했습니다.")

st.subheader("매물 검색")
f1, f2, f3, f4 = st.columns(4)
with f1:
    search = st.text_input("매물 검색", placeholder="매물명, 메모, 용도지역")
with f2:
    region_search = st.text_input("지역 검색", placeholder="화성시, 서울 등")
with f3:
    regions = sorted(st.session_state.listings["지역"].dropna().astype(str).unique())
    region_filter = st.multiselect("지역 필터", regions)
with f4:
    sort_order = st.selectbox(
        "정렬", ["입력 순", "매매가 낮은 순", "매매가 높은 순", "수익률 높은 순"]
    )

filtered = st.session_state.listings.copy()
if search:
    text = (
        filtered[["매물명", "주소", "용도지역", "메모", "투자의견"]]
        .fillna("")
        .astype(str)
        .agg(" ".join, axis=1)
    )
    filtered = filtered[text.str.contains(search, case=False, na=False)]
if region_search:
    filtered = filtered[
        filtered["주소"].astype(str).str.contains(region_search, case=False, na=False)
    ]
if region_filter:
    filtered = filtered[filtered["지역"].isin(region_filter)]
if sort_order == "매매가 낮은 순":
    filtered = filtered.sort_values("매매가(만원)")
elif sort_order == "매매가 높은 순":
    filtered = filtered.sort_values("매매가(만원)", ascending=False)
elif sort_order == "수익률 높은 순":
    filtered = filtered.sort_values("월세 수익률(%)", ascending=False)

tabs = st.tabs(["전체", *PROPERTY_TYPES])
with tabs[0]:
    show_table(filtered, "전체")
for index, property_type in enumerate(PROPERTY_TYPES, start=1):
    with tabs[index]:
        show_table(filtered[filtered["매물종류"] == property_type], property_type)

st.info(
    "Streamlit Community Cloud의 로컬 CSV 저장은 영구 보장되지 않습니다. "
    "휴대폰에서 사용한 뒤 전체 CSV를 다운로드해 백업하세요."
)
