<<<<<<< HEAD
import base64
import hmac
import json
import re
from html import unescape
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
=======
import hmac
from pathlib import Path
>>>>>>> 6b61f5762b97e3c22446bf2ee6f478d968926922

import pandas as pd
import streamlit as st


DATA_FILE = Path(__file__).with_name("listings.csv")
PYEONG = 3.3058
<<<<<<< HEAD
PROPERTY_TYPES = [
    "공장", "창고", "토지", "상가", "원룸", "투룸", "쓰리룸",
    "아파트", "빌라", "오피스텔", "사무실", "기타",
]
DEAL_TYPES = ["매매", "전세", "월세"]
RESIDENTIAL_TYPES = ["원룸", "투룸", "쓰리룸", "아파트", "빌라", "오피스텔"]
FACTORY_TYPES = ["공장", "창고"]

COLUMNS = [
    "매물명", "주소", "지역", "매물종류", "거래유형", "네이버부동산 링크",
    "사진 파일명", "사진 데이터", "매매가(만원)", "보증금(만원)", "월세(만원)",
    "관리비(만원)", "권리금(만원)", "대지면적(㎡)", "전용면적(㎡)", "공급면적(㎡)",
    "건축면적(㎡)", "건물면적(㎡)", "대지면적(평)", "전용면적(평)", "공급면적(평)",
    "건물면적(평)", "평당가 기준", "평당가(만원)", "월세 수익률(%)", "전세가율(%)",
    "매매가 대비 보증금 비율(%)", "방 개수", "욕실 수", "층수", "주차 가능 여부",
    "엘리베이터", "옵션", "준공연도", "용도지역", "업종 제한", "유동인구 메모",
    "지목", "도로 접함 여부", "개발 가능성 메모", "진입도로 폭(m)", "전력량(kW)",
    "상수도", "하수도", "호이스트", "폐수 가능 여부", "공장등록 가능 여부",
    "대형차 진입 가능 여부", "건폐율(%)", "용적률(%)", "전력당 가격(만원/kW)",
=======
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
>>>>>>> 6b61f5762b97e3c22446bf2ee6f478d968926922
    "메모",
]

NUMBER_COLUMNS = [
<<<<<<< HEAD
    "매매가(만원)", "보증금(만원)", "월세(만원)", "관리비(만원)", "권리금(만원)",
    "대지면적(㎡)", "전용면적(㎡)", "공급면적(㎡)", "건축면적(㎡)", "건물면적(㎡)",
    "방 개수", "욕실 수", "층수", "준공연도", "진입도로 폭(m)", "전력량(kW)",
=======
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
>>>>>>> 6b61f5762b97e3c22446bf2ee6f478d968926922
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


<<<<<<< HEAD
def encode_photo(photo):
    if photo is None:
        return "", ""
    encoded = base64.b64encode(photo.getvalue()).decode("ascii")
    return photo.name, f"data:{photo.type};base64,{encoded}"


def decode_photo(photo_data):
    return base64.b64decode(str(photo_data).split(",", 1)[1])


def parse_price(value):
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").replace(" ", "")
    if not text:
        return 0.0
    total = 0.0
    eok = re.search(r"(\d+(?:\.\d+)?)억", text)
    manwon = re.search(r"(\d+(?:\.\d+)?)만", text)
    if eok:
        total += float(eok.group(1)) * 10000
    if manwon:
        total += float(manwon.group(1))
    if total:
        return total
    number = re.search(r"\d+(?:\.\d+)?", text)
    return float(number.group()) if number else 0.0


def collect_json_objects(value, result):
    if isinstance(value, dict):
        result.append(value)
        for child in value.values():
            collect_json_objects(child, result)
    elif isinstance(value, list):
        for child in value:
            collect_json_objects(child, result)


def first_value(objects, keys):
    for obj in objects:
        for key in keys:
            value = obj.get(key)
            if value not in [None, "", [], {}]:
                return value
    return ""


def normalize_property_type(value):
    text = str(value)
    mapping = {
        "공장": "공장", "창고": "창고", "토지": "토지", "상가": "상가",
        "원룸": "원룸", "투룸": "투룸", "쓰리룸": "쓰리룸", "아파트": "아파트",
        "빌라": "빌라", "오피스텔": "오피스텔", "사무실": "사무실",
    }
    for keyword, property_type in mapping.items():
        if keyword in text:
            return property_type
    return "기타"


def normalize_deal_type(value):
    text = str(value)
    for deal_type in DEAL_TYPES:
        if deal_type in text:
            return deal_type
    return "매매"


def extract_naver_listing(url):
    parsed = urlparse(url.strip())
    if parsed.scheme not in ["http", "https"] or not parsed.netloc.endswith("naver.com"):
        return None

    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/124 Safari/537.36"
            )
        },
    )
    with urlopen(request, timeout=10) as response:
        html = response.read().decode("utf-8", errors="ignore")
    objects = []
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.I | re.S)
    for script_text in scripts:
        try:
            collect_json_objects(json.loads(script_text), objects)
        except (json.JSONDecodeError, TypeError):
            for match in re.findall(r"\{.*?\}", script_text):
                try:
                    collect_json_objects(json.loads(match), objects)
                except (json.JSONDecodeError, TypeError):
                    continue

    page_text = re.sub(r"<[^>]+>", " ", unescape(html))
    page_text = re.sub(r"\s+", " ", page_text).strip()
    address = first_value(objects, ["roadAddress", "jibunAddress", "address", "location"])
    property_type = normalize_property_type(
        first_value(objects, ["realEstateTypeName", "articleName", "buildingTypeName"])
    )
    deal_type = normalize_deal_type(first_value(objects, ["tradeTypeName", "tradeType"]))
    result = {
        "주소": str(address),
        "매물종류": property_type,
        "거래유형": deal_type,
        "매매가(만원)": parse_price(
            first_value(objects, ["dealOrWarrantPrc", "dealPrice", "price"])
        ),
        "보증금(만원)": parse_price(
            first_value(objects, ["warrantPrice", "deposit", "depositPrice"])
        ),
        "월세(만원)": parse_price(first_value(objects, ["rentPrc", "rentPrice", "monthlyRent"])),
        "관리비(만원)": parse_price(first_value(objects, ["maintenanceFee", "manageCost"])),
        "전용면적(㎡)": parse_price(first_value(objects, ["area2", "exclusiveArea"])),
        "공급면적(㎡)": parse_price(first_value(objects, ["area1", "supplyArea"])),
        "대지면적(㎡)": parse_price(first_value(objects, ["landArea"])),
        "건물면적(㎡)": parse_price(first_value(objects, ["buildingArea", "totalArea"])),
        "층수": parse_price(first_value(objects, ["floorInfo", "floor", "correspondingFloorCount"])),
        "방 개수": parse_price(first_value(objects, ["roomCount", "roomCnt"])),
        "욕실 수": parse_price(first_value(objects, ["bathroomCount", "bathroomCnt"])),
        "주차 가능 여부": "가능"
        if str(first_value(objects, ["parkingPossibleYN", "parkingCount"])).upper() not in ["", "N", "0"]
        else "미확인",
        "엘리베이터": "있음"
        if str(first_value(objects, ["elevatorYN", "elevatorCount"])).upper() not in ["", "N", "0"]
        else "미확인",
    }
    if not address:
        address_match = re.search(r"([가-힣]+(?:시|도)\s+[가-힣]+(?:시|군|구)[^|]{0,50})", page_text)
        if address_match:
            result["주소"] = address_match.group(1).strip()
    meaningful = sum(bool(value) for key, value in result.items() if key not in ["매물종류", "거래유형"])
    return result if meaningful else None


def option_index(options, value):
    return options.index(value) if value in options else 0


def select_price_area(row):
    property_type = row["매물종류"]
    if property_type == "토지":
        candidates = [("대지면적", row["대지면적(㎡)"])]
    elif property_type in FACTORY_TYPES:
        candidates = [
            ("건물면적", row["건물면적(㎡)"]),
            ("대지면적", row["대지면적(㎡)"]),
        ]
    else:
        candidates = [
            ("전용면적", row["전용면적(㎡)"]),
            ("건물면적", row["건물면적(㎡)"]),
            ("공급면적", row["공급면적(㎡)"]),
            ("대지면적", row["대지면적(㎡)"]),
        ]
    for name, area in candidates:
        if area > 0:
            return name, area / PYEONG
    return "면적 미입력", 0
=======
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
>>>>>>> 6b61f5762b97e3c22446bf2ee6f478d968926922


def calculate(row):
    sale_price = row["매매가(만원)"]
    deposit = row["보증금(만원)"]
    monthly_rent = row["월세(만원)"]
<<<<<<< HEAD
    investment = sale_price - deposit
    area_name, price_pyeong = select_price_area(row)

    result = {
        "대지면적(평)": round(row["대지면적(㎡)"] / PYEONG, 2),
        "전용면적(평)": round(row["전용면적(㎡)"] / PYEONG, 2),
        "공급면적(평)": round(row["공급면적(㎡)"] / PYEONG, 2),
        "건물면적(평)": round(row["건물면적(㎡)"] / PYEONG, 2),
        "평당가 기준": area_name,
        "평당가(만원)": round(sale_price / price_pyeong, 2) if price_pyeong else 0,
        "월세 수익률(%)": round(monthly_rent * 12 / investment * 100, 2)
        if investment > 0
        else 0,
        "전세가율(%)": round(deposit / sale_price * 100, 2)
        if row["거래유형"] == "전세" and sale_price > 0
        else 0,
        "매매가 대비 보증금 비율(%)": round(deposit / sale_price * 100, 2)
        if sale_price > 0
        else 0,
        "건폐율(%)": round(row["건축면적(㎡)"] / row["대지면적(㎡)"] * 100, 2)
        if row["대지면적(㎡)"] > 0
        else 0,
        "용적률(%)": round(row["건물면적(㎡)"] / row["대지면적(㎡)"] * 100, 2)
        if row["대지면적(㎡)"] > 0
        else 0,
        "전력당 가격(만원/kW)": round(sale_price / row["전력량(kW)"], 2)
        if row["전력량(kW)"] > 0
        else 0,
    }
    return result
=======
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
>>>>>>> 6b61f5762b97e3c22446bf2ee6f478d968926922


def prepare_listings(data):
    data = data.copy()
<<<<<<< HEAD
    rename_map = {"네이버부동산 URL": "네이버부동산 링크"}
    data = data.rename(columns=rename_map)
    for column in COLUMNS:
        if column not in data.columns:
            data[column] = 0 if column in NUMBER_COLUMNS else ""
    data["매물종류"] = data["매물종류"].replace("", "기타").fillna("기타")
    data["거래유형"] = data["거래유형"].replace("", "매매").fillna("매매")
    for column in NUMBER_COLUMNS:
        data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0)
=======
    for column in COLUMNS:
        if column not in data.columns:
            data[column] = 0 if column in NUMBER_COLUMNS else ""

    data["매물종류"] = data["매물종류"].replace("", "공장").fillna("공장")
    for column in NUMBER_COLUMNS:
        data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0)
    for column in FACTORY_SELECT_COLUMNS:
        data[column] = data[column].replace("", "미확인").fillna("미확인")
>>>>>>> 6b61f5762b97e3c22446bf2ee6f478d968926922

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
<<<<<<< HEAD
    st.title("전체 부동산 매물 관리")
=======
    st.title("개인용 부동산 매물 관리")
>>>>>>> 6b61f5762b97e3c22446bf2ee6f478d968926922
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
<<<<<<< HEAD
    table = data.drop(columns=["사진 데이터"], errors="ignore")
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "네이버부동산 링크": st.column_config.LinkColumn(
                "네이버부동산", display_text="매물 열기"
            ),
            "평당가(만원)": st.column_config.NumberColumn(format="%,.2f"),
            "월세 수익률(%)": st.column_config.NumberColumn(format="%.2f%%"),
            "전세가율(%)": st.column_config.NumberColumn(format="%.2f%%"),
            "매매가 대비 보증금 비율(%)": st.column_config.NumberColumn(format="%.2f%%"),
=======
    st.dataframe(
        data,
        use_container_width=True,
        hide_index=True,
        column_config={
            "분석점수": st.column_config.ProgressColumn(min_value=0, max_value=100),
            "투자의견": st.column_config.TextColumn(width="large"),
>>>>>>> 6b61f5762b97e3c22446bf2ee6f478d968926922
        },
    )
    csv_data = data.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
<<<<<<< HEAD
        "현재 목록 CSV 다운로드", csv_data, f"부동산_매물목록_{key}.csv",
        "text/csv", key=f"download_{key}",
    )
    photos = data[data["사진 데이터"].astype(str).str.startswith("data:image")]
    if not photos.empty:
        options = {
            f"{index + 1}. {row['매물명']}": row["사진 데이터"]
            for index, row in photos.reset_index(drop=True).iterrows()
        }
        selected = st.selectbox(
            "사진 확인", ["선택하지 않음", *options.keys()], key=f"photo_{key}"
        )
        if selected != "선택하지 않음":
            st.image(decode_photo(options[selected]), caption=selected, width=600)


st.set_page_config(page_title="전체 부동산 매물 관리", layout="wide")
st.markdown(
    """
    <style>
    .block-container {padding-top: 1.8rem; max-width: 1550px;}
=======
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
>>>>>>> 6b61f5762b97e3c22446bf2ee6f478d968926922
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

<<<<<<< HEAD
st.title("전체 부동산 매물 관리")
st.caption("주거·상업·토지·공장 매물을 한 곳에서 관리합니다.")
=======
st.title("개인용 부동산 매물 관리")
st.caption("공장·토지·상가·원룸을 기록하고 가격과 수익성을 자동 계산합니다.")
>>>>>>> 6b61f5762b97e3c22446bf2ee6f478d968926922

if "listings" not in st.session_state:
    st.session_state.listings = load_listings()

<<<<<<< HEAD
data = st.session_state.listings
total = len(data)
m1, m2, m3, m4 = st.columns(4)
m1.metric("전체 매물", f"{total:,}개")
m2.metric("평균 매매가", f"{data['매매가(만원)'].mean() if total else 0:,.0f}만원")
m3.metric("평균 수익률", f"{data['월세 수익률(%)'].mean() if total else 0:.2f}%")
m4.metric("등록 지역", f"{data['지역'].nunique() if total else 0:,}곳")

with st.expander("CSV 불러오기 / 전체 다운로드"):
    uploaded_csv = st.file_uploader("매물 CSV 불러오기", type="csv", key="csv_upload")
    if uploaded_csv is not None and st.button("CSV 적용"):
        try:
            st.session_state.listings = prepare_listings(read_csv_file(uploaded_csv))
=======
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
>>>>>>> 6b61f5762b97e3c22446bf2ee6f478d968926922
            save_listings(st.session_state.listings)
            st.success(f"{len(st.session_state.listings):,}개 매물을 불러왔습니다.")
        except Exception as error:
            st.error(f"CSV를 불러오지 못했습니다: {error}")
    all_csv = st.session_state.listings.to_csv(index=False).encode("utf-8-sig")
    st.download_button("전체 CSV 다운로드", all_csv, "부동산_전체매물.csv", "text/csv")

<<<<<<< HEAD
st.subheader("새 매물 등록")
url_1, url_2 = st.columns([4, 1])
with url_1:
    extraction_url = st.text_input(
        "네이버부동산 매물 URL",
        value=st.session_state.get("naver_extract_url", ""),
        placeholder="https://new.land.naver.com/...",
    )
with url_2:
    st.write("")
    st.write("")
    extract_clicked = st.button("URL 자동 추출", use_container_width=True)

if extract_clicked:
    try:
        extracted = extract_naver_listing(extraction_url)
    except Exception:
        extracted = None
    if extracted:
        st.session_state.extracted_listing = extracted
        st.session_state.naver_extract_url = extraction_url
        st.success("가능한 매물 정보를 자동 입력했습니다. 저장 전에 내용을 확인해주세요.")
    else:
        st.session_state.extracted_listing = {}
        st.warning("자동 추출 실패, 직접 입력해주세요")

auto = st.session_state.get("extracted_listing", {})
selected_type = st.selectbox(
    "등록할 매물종류",
    PROPERTY_TYPES,
    index=option_index(PROPERTY_TYPES, auto.get("매물종류", "공장")),
)

with st.form("listing_form", clear_on_submit=True):
    common_1, common_2, common_3 = st.columns(3)
    with common_1:
        st.markdown("#### 기본 정보")
        name = st.text_input("매물명 *")
        deal_type = st.selectbox(
            "거래유형", DEAL_TYPES, index=option_index(DEAL_TYPES, auto.get("거래유형", "매매"))
        )
        address = st.text_input("주소", value=str(auto.get("주소", "")))
        naver_link = st.text_input("네이버부동산 링크", value=extraction_url)
        memo = st.text_area("메모", height=100)
    with common_2:
        st.markdown("#### 금액")
        sale_price = st.number_input(
            "매매가(만원)", min_value=0.0, value=float(auto.get("매매가(만원)", 0)), step=1000.0
        )
        deposit = st.number_input(
            "보증금(만원)", min_value=0.0, value=float(auto.get("보증금(만원)", 0)), step=100.0
        )
        monthly_rent = st.number_input(
            "월세(만원)", min_value=0.0, value=float(auto.get("월세(만원)", 0)), step=10.0
        )
        maintenance_fee = st.number_input(
            "관리비(만원)", min_value=0.0, value=float(auto.get("관리비(만원)", 0)), step=1.0
        )
        photo = st.file_uploader("매물 사진", type=["jpg", "jpeg", "png", "webp"])
    with common_3:
        st.markdown("#### 면적·공통 시설")
        land_area = st.number_input(
            "대지면적(㎡)", min_value=0.0, value=float(auto.get("대지면적(㎡)", 0)), step=1.0
        )
        exclusive_area = st.number_input(
            "전용면적(㎡)", min_value=0.0, value=float(auto.get("전용면적(㎡)", 0)), step=1.0
        )
        supply_area = st.number_input(
            "공급면적(㎡)", min_value=0.0, value=float(auto.get("공급면적(㎡)", 0)), step=1.0
        )
        building_area = st.number_input(
            "건물면적/연면적(㎡)", min_value=0.0, value=float(auto.get("건물면적(㎡)", 0)), step=1.0
        )
        floor = st.number_input("층수", min_value=0, value=int(auto.get("층수", 0)), step=1)
        parking_options = ["미확인", "가능", "불가"]
        elevator_options = ["미확인", "있음", "없음"]
        parking = st.selectbox(
            "주차 가능 여부", parking_options,
            index=option_index(parking_options, auto.get("주차 가능 여부", "미확인")),
        )
        elevator = st.selectbox(
            "엘리베이터", elevator_options,
            index=option_index(elevator_options, auto.get("엘리베이터", "미확인")),
        )

    extra = {
        "방 개수": 0, "욕실 수": 0, "옵션": "", "준공연도": 0, "권리금(만원)": 0,
        "업종 제한": "", "유동인구 메모": "", "지목": "", "용도지역": "",
        "도로 접함 여부": "", "개발 가능성 메모": "", "건축면적(㎡)": 0,
        "진입도로 폭(m)": 0, "전력량(kW)": 0, "상수도": "", "하수도": "",
        "호이스트": "", "폐수 가능 여부": "", "공장등록 가능 여부": "",
        "대형차 진입 가능 여부": "",
    }

    st.markdown(f"#### {selected_type} 추가 정보")
    if selected_type in RESIDENTIAL_TYPES:
        c1, c2, c3, c4 = st.columns(4)
        extra["방 개수"] = c1.number_input(
            "방 개수", min_value=0, value=int(auto.get("방 개수", 0)), step=1
        )
        extra["욕실 수"] = c2.number_input(
            "욕실 수", min_value=0, value=int(auto.get("욕실 수", 0)), step=1
        )
        extra["준공연도"] = c3.number_input("준공연도", min_value=0, max_value=2100, step=1)
        extra["옵션"] = c4.text_input("옵션")
    elif selected_type == "상가":
        c1, c2, c3 = st.columns(3)
        extra["권리금(만원)"] = c1.number_input("권리금(만원)", min_value=0.0, step=100.0)
        extra["업종 제한"] = c2.text_input("업종 제한")
        extra["유동인구 메모"] = c3.text_area("유동인구 메모")
    elif selected_type == "토지":
        c1, c2, c3, c4 = st.columns(4)
        extra["지목"] = c1.text_input("지목")
        extra["용도지역"] = c2.text_input("용도지역")
        extra["도로 접함 여부"] = c3.selectbox("도로 접함 여부", ["미확인", "접함", "접하지 않음"])
        extra["개발 가능성 메모"] = c4.text_area("개발 가능성 메모")
    elif selected_type in FACTORY_TYPES:
        c1, c2, c3, c4 = st.columns(4)
        extra["용도지역"] = c1.text_input("용도지역")
        extra["건축면적(㎡)"] = c1.number_input("건축면적(㎡)", min_value=0.0, step=1.0)
        extra["준공연도"] = c1.number_input("준공연도", min_value=0, max_value=2100, step=1)
        extra["진입도로 폭(m)"] = c2.number_input("진입도로 폭(m)", min_value=0.0, step=0.5)
        extra["전력량(kW)"] = c2.number_input("전력량(kW)", min_value=0.0, step=10.0)
        extra["상수도"] = c3.selectbox("상수도", ["미확인", "있음", "없음"])
        extra["하수도"] = c3.selectbox("하수도", ["미확인", "있음", "없음"])
        extra["호이스트"] = c3.selectbox("호이스트", ["미확인", "있음", "없음"])
        extra["폐수 가능 여부"] = c4.selectbox("폐수 가능 여부", ["미확인", "가능", "불가"])
        extra["공장등록 가능 여부"] = c4.selectbox("공장등록 가능 여부", ["미확인", "가능", "불가"])
        extra["대형차 진입 가능 여부"] = c4.selectbox("대형차 진입 가능 여부", ["미확인", "가능", "불가"])
    elif selected_type == "사무실":
        c1, c2 = st.columns(2)
        extra["준공연도"] = c1.number_input("준공연도", min_value=0, max_value=2100, step=1)
        extra["옵션"] = c2.text_input("시설·옵션")

    submitted = st.form_submit_button("매물 저장", use_container_width=True)
=======
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
>>>>>>> 6b61f5762b97e3c22446bf2ee6f478d968926922

if submitted:
    if not name.strip():
        st.error("매물명을 입력하세요.")
<<<<<<< HEAD
    else:
        photo_name, photo_data = encode_photo(photo)
        row = {
            "매물명": name.strip(), "주소": address.strip(), "지역": get_region(address),
            "매물종류": selected_type, "거래유형": deal_type,
            "네이버부동산 링크": naver_link.strip(), "사진 파일명": photo_name,
            "사진 데이터": photo_data, "매매가(만원)": sale_price,
            "보증금(만원)": deposit, "월세(만원)": monthly_rent,
            "관리비(만원)": maintenance_fee, "대지면적(㎡)": land_area,
            "전용면적(㎡)": exclusive_area, "공급면적(㎡)": supply_area,
            "건물면적(㎡)": building_area, "층수": floor,
            "주차 가능 여부": parking, "엘리베이터": elevator, "메모": memo.strip(),
            **extra,
=======
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
>>>>>>> 6b61f5762b97e3c22446bf2ee6f478d968926922
        }
        row.update(calculate(row))
        st.session_state.listings = pd.concat(
            [st.session_state.listings, pd.DataFrame([row])], ignore_index=True
        ).reindex(columns=COLUMNS)
        save_listings(st.session_state.listings)
<<<<<<< HEAD
        st.session_state.extracted_listing = {}
        st.session_state.naver_extract_url = ""
        st.success("매물을 저장했습니다.")

st.subheader("검색 및 필터")
f1, f2, f3, f4 = st.columns(4)
with f1:
    keyword = st.text_input("키워드 검색", placeholder="매물명, 주소, 메모, 옵션")
    type_filter = st.multiselect("매물종류", PROPERTY_TYPES)
with f2:
    regions = sorted(st.session_state.listings["지역"].dropna().astype(str).unique())
    region_filter = st.multiselect("지역", regions)
    deal_filter = st.multiselect("거래유형", DEAL_TYPES)
with f3:
    min_price = st.number_input("최소 매매가(만원)", min_value=0.0, step=1000.0)
    max_price = st.number_input("최대 매매가(만원, 0=제한없음)", min_value=0.0, step=1000.0)
with f4:
    min_rent = st.number_input("최소 월세(만원)", min_value=0.0, step=10.0)
    max_rent = st.number_input("최대 월세(만원, 0=제한없음)", min_value=0.0, step=10.0)
    sort_order = st.selectbox(
        "정렬", ["입력 순", "수익률 높은 순", "평당가 낮은 순", "매매가 낮은 순", "매매가 높은 순"]
    )

filtered = st.session_state.listings.copy()
if keyword:
    search_columns = [
        "매물명", "주소", "지역", "메모", "옵션", "용도지역", "업종 제한",
        "유동인구 메모", "개발 가능성 메모",
    ]
    text = filtered[search_columns].fillna("").astype(str).agg(" ".join, axis=1)
    filtered = filtered[text.str.contains(keyword, case=False, na=False)]
if type_filter:
    filtered = filtered[filtered["매물종류"].isin(type_filter)]
if region_filter:
    filtered = filtered[filtered["지역"].isin(region_filter)]
if deal_filter:
    filtered = filtered[filtered["거래유형"].isin(deal_filter)]
filtered = filtered[filtered["매매가(만원)"] >= min_price]
filtered = filtered[filtered["월세(만원)"] >= min_rent]
if max_price > 0:
    filtered = filtered[filtered["매매가(만원)"] <= max_price]
if max_rent > 0:
    filtered = filtered[filtered["월세(만원)"] <= max_rent]

sort_map = {
    "수익률 높은 순": ("월세 수익률(%)", False),
    "평당가 낮은 순": ("평당가(만원)", True),
    "매매가 낮은 순": ("매매가(만원)", True),
    "매매가 높은 순": ("매매가(만원)", False),
}
if sort_order in sort_map:
    column, ascending = sort_map[sort_order]
    filtered = filtered.sort_values(column, ascending=ascending)
=======
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
>>>>>>> 6b61f5762b97e3c22446bf2ee6f478d968926922

tabs = st.tabs(["전체", *PROPERTY_TYPES])
with tabs[0]:
    show_table(filtered, "전체")
for index, property_type in enumerate(PROPERTY_TYPES, start=1):
    with tabs[index]:
        show_table(filtered[filtered["매물종류"] == property_type], property_type)

st.info(
<<<<<<< HEAD
    "Streamlit Community Cloud 내부 CSV는 영구 저장이 보장되지 않습니다. "
    "사용 후 전체 CSV를 다운로드해 백업하세요."
=======
    "Streamlit Community Cloud의 로컬 CSV 저장은 영구 보장되지 않습니다. "
    "휴대폰에서 사용한 뒤 전체 CSV를 다운로드해 백업하세요."
>>>>>>> 6b61f5762b97e3c22446bf2ee6f478d968926922
)
