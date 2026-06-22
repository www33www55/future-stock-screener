import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import twstock
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="未來小股神90分選股器", layout="wide")

st.title("🚀 未來小股神｜90分選股器")
st.write("掃描上市＋上櫃，找主升段、N字第二波、圓弧底強勢股")

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

def detect_n_pattern(df):
    if len(df) < 50:
        return False

    close = df["Close"]
    left_high = close.iloc[-50:-25].max()
    pullback_low = close.iloc[-25:-8].min()
    recent_close = close.iloc[-1]

    if left_high <= 0:
        return False

    pullback_depth = (left_high - pullback_low) / left_high
    has_pullback = 0.03 <= pullback_depth <= 0.25
    back_near_high = recent_close >= left_high * 0.97

    return has_pullback and back_near_high

def detect_round_bottom(df):
    if len(df) < 80:
        return False

    close = df["Close"]
    ma20 = close.rolling(20).mean()

    left = close.iloc[-80:-55].mean()
    bottom = close.iloc[-55:-25].mean()
    right = close.iloc[-25:].mean()

    bottom_lower = bottom < left * 0.95
    right_recover = right > bottom * 1.05
    ma20_turn_up = ma20.iloc[-1] > ma20.iloc[-10]

    return bottom_lower and right_recover and ma20_turn_up

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
    if body == 0:
        body = 0.01

    return last["High"] > prev_high and last["Close"] < prev_high and upper_shadow > body * 2

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

        # 趨勢 25分
        if close > last["MA20"]:
            score += 8
            reasons.append("站
