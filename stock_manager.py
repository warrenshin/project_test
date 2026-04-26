import sys
import feedparser
from deep_translator import GoogleTranslator
from colorama import init, Fore, Style
from tabulate import tabulate
import matplotlib.pyplot as plt
import matplotlib
import pandas as pd
import urllib.request

matplotlib.rcParams["font.family"] = "Malgun Gothic"
matplotlib.rcParams["axes.unicode_minus"] = False

init(autoreset=True)

sys.stdout.reconfigure(encoding="utf-8")

SHEETS_URL = "https://docs.google.com/spreadsheets/d/1BBA17TGKqHCDQXcKXqNP2Xh4Fk_um6u3/export?format=csv&gid=624003189"
CSV_PATH = r"C:\work\project_test\주식상황_new.csv"


def download_csv():
    try:
        print("  구글 스프레드시트에서 데이터 다운로드 중...", end=" ", flush=True)
        urllib.request.urlretrieve(SHEETS_URL, CSV_PATH)
        print("완료")
    except Exception as e:
        print(f"실패 ({e}) → 기존 파일 사용")
        fallback = r"C:\work\project_test\주식상황1.xlsx - 시트1.csv"
        import os
        if not os.path.exists(CSV_PATH) and os.path.exists(fallback):
            import shutil
            shutil.copy(fallback, CSV_PATH)

COLS = {
    "종목": "종목",
    "현재": "현재가",
    "전일비(%)": "전일비",
    "평균매수금": "평균매수가",
    "수익율": "수익율",
    "보유": "보유수량",
    "평가손익": "평가손익",
    "실현손익": "실현손익",
    "총손익": "총손익",
    "비중": "비중",
    "평가액": "평가액",
}

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


def load_data():
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

    # 수익율이 비정상적으로 큰 행(펀드/현금 등 합산행) 제외
    df = df[df["수익율_num"].abs() < 1000]

    # 총손익이 0인 데이터 제외 (현금 자산 제외)
    is_special = df["종목"].str.contains("현금|펀드", na=False)
    df = df[is_special | (df["총손익_num"] != 0)]

    # 중복 종목 제거 (첫 번째 항목 유지)
    df = df.drop_duplicates(subset="종목", keep="first")

    return df.reset_index(drop=True)


def fmt_money(val):
    if val == 0:
        return "-"
    sign = "-₩" if val < 0 else "₩"
    return f"{sign}{abs(val):>12,.0f}"


def fmt_holding(val):
    try:
        v = float(val)
        return "-" if v == 0 else f"{int(v):,}"
    except (ValueError, TypeError):
        return "-"


def print_table(df, title):
    print(f"\n  {title}  ({len(df)}개 종목)")

    rows = []
    for _, row in df.iterrows():
        pct = row["수익율_num"]
        arrow = "▲" if pct > 0 else ("▼" if pct < 0 else " ")
        pct_str = f"{arrow} {abs(pct):.2f}%"

        if pct > 0:
            colored_pct = f"{Fore.RED}{pct_str}{Style.RESET_ALL}"
            colored_name = f"{Fore.RED}{row['종목']}{Style.RESET_ALL}"
        elif pct < 0:
            colored_pct = f"{Fore.BLUE}{pct_str}{Style.RESET_ALL}"
            colored_name = f"{Fore.BLUE}{row['종목']}{Style.RESET_ALL}"
        else:
            colored_pct = pct_str
            colored_name = row["종목"]

        day_pct = row["전일비_num"]
        day_arrow = "▲" if day_pct > 0 else ("▼" if day_pct < 0 else " ")
        day_str = f"{day_arrow} {abs(day_pct):.2f}%"
        if day_pct > 0:
            colored_day = f"{Fore.RED}{day_str}{Style.RESET_ALL}"
        elif day_pct < 0:
            colored_day = f"{Fore.BLUE}{day_str}{Style.RESET_ALL}"
        else:
            colored_day = day_str

        rows.append([
            colored_name,
            fmt_money(row["현재가_num"]),
            colored_day,
            fmt_money(row["평균매수가_num"]),
            colored_pct,
            fmt_holding(row["보유수량"]),
            f"{row['비중_num']:.1f}%",
            fmt_money(row["총손익_num"]),
            fmt_money(row["평가액_num"]),
        ])

    headers = ["종목", "현재가", "전일비", "평균매수가", "수익율", "보유", "비중", "총손익", "평가액"]
    print(tabulate(rows, headers=headers, tablefmt="double_outline", stralign="right", numalign="right"))
    print()


def summary(df):
    total_val = df["평가액_num"].sum()
    total_gain = df["총손익_num"].sum()
    total_eval = df["평가손익_num"].sum()
    total_realized = df["실현손익_num"].sum()
    profit_count = (df["수익율_num"] > 0).sum()
    loss_count = (df["수익율_num"] < 0).sum()

    print(f"\n  [ 포트폴리오 요약 ]")
    print(f"  총 평가액    : ₩{total_val:>15,.0f}")
    print(f"  총 손익      : ₩{total_gain:>15,.0f}")
    print(f"  ├ 평가손익   : ₩{total_eval:>15,.0f}")
    print(f"  └ 실현손익   : ₩{total_realized:>15,.0f}")
    print(f"  수익 종목    : {profit_count}개  |  손실 종목: {loss_count}개  |  전체: {len(df)}개")
    print()


def export_csv(df, sort_label):
    out_cols = {
        "종목": "종목",
        "현재가": "현재가",
        "평균매수가": "평균매수가",
        "수익율": "수익율",
        "보유수량": "보유수량",
        "비중": "비중",
        "평가손익": "평가손익",
        "실현손익": "실현손익",
        "총손익": "총손익",
        "평가액": "평가액",
    }
    out = df[[c for c in out_cols if c in df.columns]].copy()
    out_path = r"C:\work\project_test\stock_summary.csv"
    out.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n  저장 완료 → {out_path}  ({len(out)}개 종목, 정렬: {sort_label})\n")


def show_pie_chart(df):
    data = df[df["비중_num"] > 0][["종목", "비중_num"]].copy()
    if data.empty:
        print("  비중 데이터가 없습니다.")
        return

    # 비중 1% 미만은 "기타"로 묶기
    threshold = 1.0
    small = data[data["비중_num"] < threshold]
    big   = data[data["비중_num"] >= threshold]
    if not small.empty:
        etc_row = pd.DataFrame([{"종목": f"기타 ({len(small)}개)", "비중_num": small["비중_num"].sum()}])
        data = pd.concat([big, etc_row], ignore_index=True)
    else:
        data = big

    labels = data["종목"].tolist()
    sizes  = data["비중_num"].tolist()

    fig, ax = plt.subplots(figsize=(10, 8))
    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=labels,
        autopct="%1.1f%%",
        startangle=140,
        pctdistance=0.82,
        wedgeprops=dict(linewidth=0.5, edgecolor="white"),
    )
    for t in autotexts:
        t.set_fontsize(8)
    for t in texts:
        t.set_fontsize(9)

    ax.set_title("포트폴리오 비중", fontsize=15, fontweight="bold", pad=20)
    plt.tight_layout()
    plt.show()


def fetch_yahoo_news(max_items=10):
    rss_url = "https://news.google.com/rss/search?q=stock+market+finance&hl=en-US&gl=US&ceid=US:en"
    try:
        feed = feedparser.parse(rss_url)
        articles = []
        for entry in feed.entries[:max_items]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "")
            if title:
                articles.append((title, link))
        return articles if articles else [("뉴스를 가져올 수 없습니다.", "")]
    except Exception as e:
        return [(f"뉴스 불러오기 실패: {e}", "")]


def translate_to_korean(text):
    try:
        return GoogleTranslator(source="auto", target="ko").translate(text)
    except Exception:
        return text


def print_news():
    print("\n  [ Yahoo Finance 최신 뉴스 (한국어) ]")
    print("-" * 100)
    news = fetch_yahoo_news()
    if not news:
        print("  뉴스를 가져올 수 없습니다.")
    for i, (title, link) in enumerate(news, 1):
        korean = translate_to_korean(title)
        print(f"  {i:>2}. {Fore.YELLOW}{korean}{Style.RESET_ALL}")
        if link:
            print(f"      {Fore.GREEN}{link}{Style.RESET_ALL}")
    print("-" * 100)


def fetch_cnbc_news(max_items=10):
    rss_url = "https://www.cnbc.com/id/100003114/device/rss/rss.html"
    try:
        feed = feedparser.parse(rss_url)
        articles = []
        for entry in feed.entries[:max_items]:
            title = entry.get("title", "").strip()
            summary = entry.get("summary", "").strip()
            link = entry.get("link", "")
            if title:
                articles.append((title, summary, link))
        return articles if articles else [("뉴스를 가져올 수 없습니다.", "", "")]
    except Exception as e:
        return [(f"뉴스 불러오기 실패: {e}", "", "")]


def print_cnbc_news():
    print("\n  [ CNBC 세계 경제 뉴스 (한국어 요약) ]")
    print("-" * 100)
    news = fetch_cnbc_news()
    for i, (title, summary, link) in enumerate(news, 1):
        korean_title = translate_to_korean(title)
        print(f"  {i:>2}. {Fore.YELLOW}{korean_title}{Style.RESET_ALL}")
        if summary:
            korean_summary = translate_to_korean(summary[:200])
            print(f"      {Fore.WHITE}{korean_summary}{Style.RESET_ALL}")
        if link:
            print(f"      {Fore.GREEN}{link}{Style.RESET_ALL}")
        print()
    print("-" * 100)


def fetch_fj_news(max_items=10):
    rss_url = "https://www.financialjuice.com/feed.ashx?xy=rss"
    try:
        feed = feedparser.parse(rss_url)
        articles = []
        for entry in feed.entries[:max_items]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "")
            pub = entry.get("published", "")
            if title:
                articles.append((title, pub, link))
        return articles if articles else [("뉴스를 가져올 수 없습니다.", "", "")]
    except Exception as e:
        return [(f"뉴스 불러오기 실패: {e}", "", "")]


def print_fj_news():
    print("\n  [ Financial Juice 최신 뉴스 (한국어) ]")
    print("-" * 100)
    news = fetch_fj_news()
    for i, (title, pub, link) in enumerate(news, 1):
        korean = translate_to_korean(title)
        time_str = f"  [{pub}]" if pub else ""
        print(f"  {i:>2}. {Fore.CYAN}{korean}{Style.RESET_ALL}{Fore.WHITE}{time_str}{Style.RESET_ALL}")
        if link:
            print(f"      {Fore.GREEN}{link}{Style.RESET_ALL}")
        print()
    print("-" * 100)


def menu(df):
    options = {
        "1": ("수익율 높은 순", lambda d: d.sort_values("수익율_num", ascending=False)),
        "2": ("수익율 낮은 순 (손실 먼저)", lambda d: d.sort_values("수익율_num", ascending=True)),
        "3": ("총손익 높은 순", lambda d: d.sort_values("총손익_num", ascending=False)),
        "4": ("평가액 높은 순 (비중 큰 순)", lambda d: d.sort_values("평가액_num", ascending=False)),
        "5": ("수익 종목만 (수익율 > 0)", lambda d: d[d["수익율_num"] > 0].sort_values("수익율_num", ascending=False)),
        "6": ("손실 종목만 (수익율 < 0)", lambda d: d[d["수익율_num"] < 0].sort_values("수익율_num", ascending=True)),
        "7": ("전체 목록 (원본 순서)", lambda d: d),
        "d": ("전일비 높은 순", lambda d: d.sort_values("전일비_num", ascending=False)),
        "8": ("CSV 저장", None),
        "9": ("Yahoo Finance 뉴스 보기", None),
        "c": ("CNBC 경제뉴스 보기 (한국어 요약)", None),
        "f": ("Financial Juice 최신 뉴스 (한국어)", None),
        "p": ("비중 파이차트 보기", None),
        "0": ("종료", None),
    }

    while True:
        print("  [ 메뉴 ]")
        for k, (label, _) in options.items():
            print(f"    {k}. {label}")
        choice = input("\n  선택 > ").strip()

        if choice == "0":
            print("\n  종료합니다.")
            break
        elif choice == "8":
            sort_label = input("  정렬 기준 입력 (1~7번 선택, 기본=평가액 큰 순): ").strip()
            sort_options = {
                "1": ("수익율 높은 순", lambda d: d.sort_values("수익율_num", ascending=False)),
                "2": ("수익율 낮은 순", lambda d: d.sort_values("수익율_num", ascending=True)),
                "3": ("총손익 높은 순", lambda d: d.sort_values("총손익_num", ascending=False)),
                "4": ("평가액 높은 순", lambda d: d.sort_values("평가액_num", ascending=False)),
                "5": ("수익 종목만", lambda d: d[d["수익율_num"] > 0].sort_values("수익율_num", ascending=False)),
                "6": ("손실 종목만", lambda d: d[d["수익율_num"] < 0].sort_values("수익율_num", ascending=True)),
                "7": ("원본 순서", lambda d: d),
                "d": ("전일비 높은 순", lambda d: d.sort_values("전일비_num", ascending=False)),
            }
            label, fn = sort_options.get(sort_label, ("평가액 높은 순", lambda d: d.sort_values("평가액_num", ascending=False)))
            export_csv(fn(df), label)
        elif choice == "9":
            print_news()
        elif choice == "c":
            print_cnbc_news()
        elif choice == "f":
            print_fj_news()
        elif choice == "p":
            show_pie_chart(df)
        elif choice in options:
            label, fn = options[choice]
            result = fn(df)
            print_table(result, label)
            summary(result)
        else:
            print("  올바른 번호를 입력하세요.\n")


if __name__ == "__main__":
    print("\n  주식 종목별 수익율 관리")
    download_csv()
    df = load_data()
    print_table(df.sort_values("수익율_num", ascending=False), "수익율 높은 순 (기본)")
    summary(df)
    menu(df)
