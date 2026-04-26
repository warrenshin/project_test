import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
import matplotlib.font_manager as fm
import feedparser
import urllib.request
import platform
import os
import tempfile
from deep_translator import GoogleTranslator

if platform.system() == "Windows":
    matplotlib.rcParams["font.family"] = "Malgun Gothic"
else:
    matplotlib.rcParams["font.family"] = "NanumGothic"
matplotlib.rcParams["axes.unicode_minus"] = False

SHEETS_URL = "https://docs.google.com/spreadsheets/d/1BBA17TGKqHCDQXcKXqNP2Xh4Fk_um6u3/export?format=csv&gid=624003189"
CSV_PATH = os.path.join(tempfile.gettempdir(), "주식상황_new.csv")

JUNK_PATTERNS = ["http", "xpath", "/html", "//*", "importxml", "url", "200.99"]


def is_valid_ticker(name):
    if pd.isna(name):
        return False
    s = str(name).strip().lower()
    return s and not any(p in s for p in JUNK_PATTERNS)


def parse_money(val):
    if pd.isna(val):
        return 0.0
    s = str(val).replace("₩", "").replace(",", "").replace(" ", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_pct(val):
    if pd.isna(val):
        return 0.0
    s = str(val).replace("%", "").replace(" ", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


@st.cache_data(ttl=300)
def download_and_load():
    try:
        urllib.request.urlretrieve(SHEETS_URL, CSV_PATH)
    except Exception:
        pass

    COLS = {
        "종목": "종목", "현재": "현재가", "전일비(%)": "전일비", "평균매수금": "평균매수가",
        "수익율": "수익율", "보유": "보유수량", "평가손익": "평가손익",
        "실현손익": "실현손익", "총손익": "총손익", "비중": "비중", "평가액": "평가액",
    }

    raw = pd.read_csv(CSV_PATH, encoding="utf-8-sig")
    df = raw[raw["종목"].apply(is_valid_ticker)][list(COLS.keys())].copy()
    df = df.rename(columns=COLS)

    df["수익율_num"] = df["수익율"].apply(parse_pct)
    df["전일비_num"] = df["전일비"].apply(parse_pct)
    df["비중_num"] = df["비중"].apply(parse_pct)
    df["평가액_num"] = df["평가액"].apply(parse_money)
    df["총손익_num"] = df["총손익"].apply(parse_money)
    df["평가손익_num"] = df["평가손익"].apply(parse_money)
    df["실현손익_num"] = df["실현손익"].apply(parse_money)
    df["현재가_num"] = df["현재가"].apply(parse_money)
    df["평균매수가_num"] = df["평균매수가"].apply(parse_money)

    df = df[df["수익율_num"].abs() < 1000]
    is_special = df["종목"].str.contains("현금|펀드", na=False)
    df = df[is_special | (df["총손익_num"] != 0)]
    df = df.drop_duplicates(subset="종목", keep="first")
    return df.reset_index(drop=True)


def fmt_money(val):
    if val == 0:
        return "-"
    sign = "-₩" if val < 0 else "₩"
    return f"{sign}{abs(val):,.0f}"


def fmt_pct(val):
    arrow = "▲" if val > 0 else ("▼" if val < 0 else " ")
    return f"{arrow} {abs(val):.2f}%"


@st.cache_data(ttl=600)
def fetch_news(source):
    urls = {
        "yahoo": "https://news.google.com/rss/search?q=stock+market+finance&hl=en-US&gl=US&ceid=US:en",
        "cnbc":  "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "fj":    "https://www.financialjuice.com/feed.ashx?xy=rss",
    }
    try:
        feed = feedparser.parse(urls[source])
        items = []
        for entry in feed.entries[:10]:
            title = entry.get("title", "").strip()
            summary = entry.get("summary", "").strip()
            link = entry.get("link", "")
            pub = entry.get("published", "")
            if title:
                items.append((title, summary[:200] if summary else "", link, pub))
        return items
    except Exception as e:
        return [(f"뉴스 불러오기 실패: {e}", "", "", "")]


def translate(text):
    try:
        return GoogleTranslator(source="auto", target="ko").translate(text)
    except Exception:
        return text


# ─── 앱 시작 ───────────────────────────────────────────────
st.set_page_config(
    page_title="주식 포트폴리오",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.title("📈 주식 포트폴리오 관리")

# 새로고침 버튼
col_refresh, col_time = st.columns([1, 4])
with col_refresh:
    if st.button("🔄 데이터 새로고침"):
        st.cache_data.clear()
        st.rerun()

with st.spinner("구글 스프레드시트에서 데이터 로딩 중..."):
    df = download_and_load()

# ─── 포트폴리오 요약 ───────────────────────────────────────
total_val = df["평가액_num"].sum()
total_gain = df["총손익_num"].sum()
total_eval = df["평가손익_num"].sum()
total_realized = df["실현손익_num"].sum()
profit_count = (df["수익율_num"] > 0).sum()
loss_count = (df["수익율_num"] < 0).sum()

st.subheader("📊 포트폴리오 요약")
c1, c2, c3, c4 = st.columns(4)
c1.metric("총 평가액", f"₩{total_val:,.0f}")
c2.metric("총 손익", f"₩{total_gain:,.0f}", delta=f"평가 ₩{total_eval:,.0f}")
c3.metric("실현손익", f"₩{total_realized:,.0f}")
c4.metric("종목 수", f"{len(df)}개", delta=f"수익 {profit_count} / 손실 {loss_count}")

st.divider()

# ─── 종목 테이블 ────────────────────────────────────────────
st.subheader("📋 종목 현황")

sort_options = {
    "수익율 높은 순": ("수익율_num", False),
    "수익율 낮은 순 (손실)": ("수익율_num", True),
    "전일비 높은 순": ("전일비_num", False),
    "전일비 낮은 순": ("전일비_num", True),
    "총손익 높은 순": ("총손익_num", False),
    "평가액 높은 순": ("평가액_num", False),
}

col_sort, col_filter = st.columns([2, 2])
with col_sort:
    sort_label = st.selectbox("정렬 기준", list(sort_options.keys()))
with col_filter:
    filter_option = st.selectbox("필터", ["전체", "수익 종목만", "손실 종목만"])

sort_col, sort_asc = sort_options[sort_label]
display_df = df.copy()

if filter_option == "수익 종목만":
    display_df = display_df[display_df["수익율_num"] > 0]
elif filter_option == "손실 종목만":
    display_df = display_df[display_df["수익율_num"] < 0]

display_df = display_df.sort_values(sort_col, ascending=sort_asc)

table_df = pd.DataFrame({
    "종목": display_df["종목"].values,
    "현재가": display_df["현재가_num"].apply(fmt_money).values,
    "전일비": display_df["전일비_num"].apply(fmt_pct).values,
    "평균매수가": display_df["평균매수가_num"].apply(fmt_money).values,
    "수익율": display_df["수익율_num"].apply(fmt_pct).values,
    "보유수량": display_df["보유수량"].values,
    "비중": display_df["비중_num"].apply(lambda x: f"{x:.1f}%").values,
    "평가손익": display_df["평가손익_num"].apply(fmt_money).values,
    "총손익": display_df["총손익_num"].apply(fmt_money).values,
    "평가액": display_df["평가액_num"].apply(fmt_money).values,
})


def color_pct(val):
    if "▲" in str(val):
        return "color: #FF4B4B; font-weight: bold"
    elif "▼" in str(val):
        return "color: #1E88E5; font-weight: bold"
    return ""


def color_money(val):
    s = str(val)
    if s.startswith("-₩"):
        return "color: #1E88E5"
    elif s.startswith("₩") and s != "₩0":
        return "color: #FF4B4B"
    return ""


styled = table_df.style.map(color_pct, subset=["수익율", "전일비"])
styled = styled.map(color_money, subset=["평가손익", "총손익"])
st.dataframe(styled, use_container_width=True, hide_index=True)

st.divider()

# ─── 탭: 차트 / 뉴스 ────────────────────────────────────────
tab_chart, tab_yahoo, tab_cnbc, tab_fj = st.tabs(["🥧 비중 차트", "📰 Yahoo 뉴스", "🌐 CNBC 뉴스", "⚡ Financial Juice"])

with tab_chart:
    data = df[df["비중_num"] > 0][["종목", "비중_num"]].copy()
    threshold = 1.0
    small = data[data["비중_num"] < threshold]
    big = data[data["비중_num"] >= threshold]
    if not small.empty:
        etc = pd.DataFrame([{"종목": f"기타 ({len(small)}개)", "비중_num": small["비중_num"].sum()}])
        data = pd.concat([big, etc], ignore_index=True)
    else:
        data = big

    fig, ax = plt.subplots(figsize=(8, 6))
    wedges, texts, autotexts = ax.pie(
        data["비중_num"],
        labels=data["종목"],
        autopct="%1.1f%%",
        startangle=140,
        pctdistance=0.82,
        wedgeprops=dict(linewidth=0.5, edgecolor="white"),
    )
    for t in autotexts:
        t.set_fontsize(7)
    for t in texts:
        t.set_fontsize(8)
    ax.set_title("포트폴리오 비중", fontsize=14, fontweight="bold")
    plt.tight_layout()
    st.pyplot(fig)

with tab_yahoo:
    if st.button("Yahoo 뉴스 불러오기", key="yahoo_btn"):
        with st.spinner("뉴스 번역 중..."):
            news = fetch_news("yahoo")
            for i, (title, summary, link, pub) in enumerate(news, 1):
                korean = translate(title)
                st.markdown(f"**{i}. {korean}**")
                if link:
                    st.markdown(f"🔗 [{link}]({link})")
                st.divider()

with tab_cnbc:
    if st.button("CNBC 뉴스 불러오기", key="cnbc_btn"):
        with st.spinner("CNBC 뉴스 번역 중..."):
            news = fetch_news("cnbc")
            for i, (title, summary, link, pub) in enumerate(news, 1):
                korean_title = translate(title)
                st.markdown(f"**{i}. {korean_title}**")
                if summary:
                    korean_summary = translate(summary)
                    st.caption(korean_summary)
                if link:
                    st.markdown(f"🔗 [{link}]({link})")
                st.divider()

with tab_fj:
    if st.button("Financial Juice 뉴스 불러오기", key="fj_btn"):
        with st.spinner("Financial Juice 뉴스 번역 중..."):
            news = fetch_news("fj")
            for i, (title, summary, link, pub) in enumerate(news, 1):
                korean = translate(title)
                time_str = f" `{pub}`" if pub else ""
                st.markdown(f"**{i}. {korean}**{time_str}")
                if link:
                    st.markdown(f"🔗 [{link}]({link})")
                st.divider()
