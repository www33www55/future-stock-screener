import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import twstock
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="未來小股神5.0", layout="wide")

st.title("🚀 未來小股神 5.0｜90分選股器")
st.write("自動掃描上市＋上櫃，找出主升段、N字第二波、圓弧底強勢股")

# ======================
# 股票池
# ======================

@st.cache_data
def get_all_tw_stocks():
    rows = []
    for code, info in twstock.codes.items():
        if len(code) == 4 and info.market in ["上市", "上櫃"]:
            suffix = ".TW" if info.market == "上市" else ".TWO"
            rows.append({
                "股號": code,
                "股名": info.name,
                "市場": info.market,
                "代號": code + suffix
            })
    return pd.DataFrame(rows)


# ======================
# 技術指標
# ======================

def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_kd(df, period=9):
    low_min = df["Low"].rolling(period).min()
    high_max = df["High"].rolling(period).max()
    rsv = (df["Close"] - low_min) / (high_max - low_min).replace(0, np.nan) * 100
    k = rsv.ewm(com=2).mean()
    d = k.ewm(com=2).mean()
    return k, d


def calc_macd(close):
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    return macd, signal, hist


# ======================
# 型態判斷
# ======================

def detect_n_pattern(df):
    close = df["Close"]
    if len(close) < 60:
        return False

    old_high = close.iloc[-60:-30].max()
    pullback_low = close.iloc[-30:-10].min()
    now = close.iloc[-1]

    if old_high <= 0:
        return False

    pullback_ok = pullback_low < old_high * 0.95
    breakout_ok = now > old_high * 1.01

    return pullback_ok and breakout_ok


def detect_round_bottom(df):
    if len(df) < 80:
        return False

    close = df["Close"]
    ma20 = close.rolling(20).mean()

    left = close.iloc[-80:-50].mean()
    middle = close.iloc[-50:-20].mean()
    right = close.iloc[-20:].mean()

    ma20_up = ma20.iloc[-1] > ma20.iloc[-10]
    neckline = close.iloc[-60:-10].max()
    breakout = close.iloc[-1] >= neckline * 0.98

    return middle < left and right > middle and ma20_up and breakout


def detect_kd_top_divergence(df):
    if len(df) < 40:
        return False

    recent = df.tail(40)
    price_now = recent["Close"].iloc[-1]
    price_before = recent["Close"].iloc[:-10].max()

    kd_now = recent["K"].iloc[-1]
    kd_before = recent["K"].iloc[:-10].max()

    return price_now > price_before and kd_now < kd_before


def detect_fake_breakout(df):
    if len(df) < 40:
        return False

    last = df.iloc[-1]
    prev_high = df["Close"].iloc[-40:-1].max()

    upper_shadow = last["High"] - max(last["Close"], last["Open"])
    body = abs(last["Close"] - last["Open"])

    long_upper = upper_shadow > body * 2
    breakout_fail = last["High"] > prev_high and last["Close"] < prev_high

    return long_upper and breakout_fail


def detect_big_upper_shadow(df):
    last = df.iloc[-1]
    body = abs(last["Close"] - last["Open"])
    upper_shadow = last["High"] - max(last["Close"], last["Open"])

    if body == 0:
        body = 0.01

    return upper_shadow > body * 2 and last["Volume"] > last["VOL20"] * 1.5


# ======================
# 單股評分
# ======================

def score_stock(row):
    code = row["代號"]

    try:
        df = yf.download(
            code,
            period="6mo",
            interval="1d",
            progress=False,
            auto_adjust=False,
            threads=False
        )

        if df.empty or len(df) < 90:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.dropna()

        df["MA20"] = df["Close"].rolling(20).mean()
        df["MA60"] = df["Close"].rolling(60).mean()
        df["VOL20"] = df["Volume"].rolling(20).mean()
        df["RSI"] = calc_rsi(df["Close"])
        df["K"], df["D"] = calc_kd(df)
        df["MACD"], df["SIGNAL"], df["HIST"] = calc_macd(df["Close"])

        df = df.dropna()

        if len(df) < 30:
            return None

        last = df.iloc[-1]
        prev = df.iloc[-2]

        close = float(last["Close"])
        score = 0
        reasons = []

        # 趨勢 30
        if close > last["MA20"]:
            score += 10
            reasons.append("站上月線")

        if close > last["MA60"]:
            score += 10
            reasons.append("站上季線")

        if last["MA20"] > df["MA20"].iloc[-5]:
            score += 10
            reasons.append("月線上彎")

        # MACD 20
        macd_gold = last["MACD"] > last["SIGNAL"]
        macd_above_zero = last["MACD"] > 0

        if macd_gold:
            score += 10
            reasons.append("MACD黃金交叉")

        if macd_above_zero:
            score += 10
            reasons.append("MACD在0軸上")

        # KD 15
        kd_gold = last["K"] > last["D"]

        if kd_gold:
            score += 10
            reasons.append("KD偏多")

        if last["K"] > 20:
            score += 5

        if last["K"] > 90:
            score -= 10
            reasons.append("KD過熱")

        # 量能 15
        if last["Volume"] > last["VOL20"] * 2:
            score += 15
            reasons.append("爆量2倍")
        elif last["Volume"] > last["VOL20"] * 1.5:
            score += 10
            reasons.append("量增1.5倍")

        # 型態 20
        n_pattern = detect_n_pattern(df)
        round_bottom = detect_round_bottom(df)

        if n_pattern:
            score += 10
            reasons.append("N字第二波")

        if round_bottom:
            score += 10
            reasons.append("圓弧底完成")

        # 主升段雷達
        recent_high = df["Close"].tail(40).max()
        breakout = close >= recent_high * 0.98
        main_wave = macd_above_zero and macd_gold and last["MA20"] > df["MA20"].iloc[-5] and breakout

        if main_wave:
            score += 10
            reasons.append("主升段啟動")

        # 風險扣分
        kd_div = detect_kd_top_divergence(df)
        fake_breakout = detect_fake_breakout(df)
        big_upper = detect_big_upper_shadow(df)

        if kd_div:
            score -= 20
            reasons.append("KD頂背離")

        if last["RSI"] > 90:
            score -= 20
            reasons.append("RSI過熱")

        if close < last["MA20"]:
            score -= 15
            reasons.append("跌破月線")

        if close < last["MA60"]:
            score -= 15
            reasons.append("跌破季線")

        if fake_breakout:
            score -= 20
            reasons.append("假突破")

        if big_upper:
            score -= 15
            reasons.append("爆量長上影")

        score = int(max(0, min(100, score)))

        wave_low = df["Low"].tail(30).min()
        wave_high = df["High"].tail(30).max()
        wave = wave_high - wave_low

        stop_loss = round(close * 0.94, 2)
        target1 = round(close + wave * 0.5, 2)
        target2 = round(close + wave, 2)

        breakout_rate = min(100, max(0, score + (10 if breakout else -5)))
        second_wave_rate = min(100, max(0, score + (10 if n_pattern else -10)))

        if main_wave:
            main_wave_text = "🔥 是"
        else:
            main_wave_text = "—"

        if n_pattern:
            n_text = "🔥 是"
        else:
            n_text = "—"

        if round_bottom:
            round_text = "🌙 是"
        else:
            round_text = "—"

        if score >= 90:
            advice = "✅ 強勢股，可觀察回踩進場"
        elif score >= 80:
            advice = "🟡 強勢觀察，等突破或回踩"
        else:
            advice = "🔴 暫不列入"

        return {
            "股號": row["股號"],
            "股名": row["股名"],
            "市場": row["市場"],
            "最新價": round(close, 2),
            "分數": score,
            "主升段": main_wave_text,
            "N字第二波": n_text,
            "圓弧底": round_text,
            "突破成功率": f"{breakout_rate}%",
            "第二波機率": f"{second_wave_rate}%",
            "停損價": stop_loss,
            "第一目標": target1,
            "第二目標": target2,
            "建議": advice,
            "理由": "、".join(reasons)
        }

    except Exception:
        return None


# ======================
# 介面
# ======================

stocks_df = get_all_tw_stocks()
st.success(f"股票池已載入：{len(stocks_df)} 檔")

scan_mode = st.radio(
    "掃描範圍",
    ["前100檔測試", "自訂股票池", "全上市上櫃"],
    horizontal=True
)

if scan_mode == "前100檔測試":
    scan_df = stocks_df.head(100)

elif scan_mode == "自訂股票池":
    user_input = st.text_area(
        "輸入股號，用逗號分開，例如：2330,2303,2409,2313,3037,6272,3060",
        "2330,2303,2409,2313,3037,6272,3060"
    )
    codes = [x.strip() for x in user_input.split(",") if x.strip()]
    scan_df = stocks_df[stocks_df["股號"].isin(codes)]

else:
    scan_df = stocks_df

min_score = st.slider("最低顯示分數", 70, 100, 90)
max_workers = st.slider("掃描速度", 4, 16, 8)

st.warning("全上市上櫃掃描會比較久，手機版可能需要等待數分鐘。建議先用前100檔測試。")

if st.button("🔥 開始掃描"):
    results = []
    total = len(scan_df)

    progress = st.progress(0)
    status = st.empty()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(score_stock, row) for _, row in scan_df.iterrows()]

        for i, future in enumerate(as_completed(futures)):
            result = future.result()

            if result and result["分數"] >= min_score:
                results.append(result)

            progress.progress((i + 1) / total)
            status.write(f"掃描中：{i + 1}/{total}")

    if results:
        result_df = pd.DataFrame(results)
        result_df = result_df.sort_values("分數", ascending=False).reset_index(drop=True)
        result_df.insert(0, "排名", result_df.index + 1)

        st.subheader("🏆 強勢股排行榜")
        st.dataframe(result_df, use_container_width=True)

        st.subheader("🔥 90分以上強勢股")
        top90 = result_df[result_df["分數"] >= 90]

        if not top90.empty:
            for _, r in top90.iterrows():
                st.success(
                    f"🥇 {r['股號']}｜{r['股名']}｜{r['分數']}分\n\n"
                    f"🚀 主升段：{r['主升段']}\n\n"
                    f"🔥 N字第二波：{r['N字第二波']}\n\n"
                    f"🌙 圓弧底：{r['圓弧底']}\n\n"
                    f"⭐ 突破成功率：{r['突破成功率']}\n\n"
                    f"🎯 停損：{r['停損價']}｜目標1：{r['第一目標']}｜目標2：{r['第二目標']}\n\n"
                    f"理由：{r['理由']}"
                )
        else:
            st.warning("目前沒有90分以上股票")
    else:
        st.warning("沒有符合條件的股票")
