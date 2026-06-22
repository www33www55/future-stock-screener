import streamlit as st

st.set_page_config(
    page_title="未來小股神90分選股器",
    layout="wide"
)

st.title("🚀 未來小股神90分選股器")

st.success("90分選股器啟動成功")

stocks = {
    "2330.TW": "台積電",
    "2303.TW": "聯電",
    "2409.TW": "友達",
    "2313.TW": "華通",
    "3037.TW": "欣興",
    "6272.TW": "同欣電",
    "3060.TW": "銘異"
}

st.header("🔥 今日觀察清單")

for code, name in stocks.items():
    st.write(f"📈 {code} ｜ {name}")

st.divider()

st.header("🏆 強勢股排行榜（示範版）")

ranking = [
    ("3037.TW", "欣興", 94),
    ("2313.TW", "華通", 92),
    ("2409.TW", "友達", 91),
    ("6272.TW", "同欣電", 89),
    ("2303.TW", "聯電", 88),
]

for i, (code, name, score) in enumerate(ranking, start=1):
    st.write(f"{i}. {code} ｜ {name} ｜ ⭐ {score}分")

st.divider()

st.success("下一版將加入：MACD、KD背離、N字第二波、90分自動篩選")
