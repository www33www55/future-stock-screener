import streamlit as st

st.set_page_config(page_title="未來小股神90分選股器")

st.title("🚀 未來小股神90分選股器")

st.success("90分選股器啟動成功")

stocks = [
    "2330.TW",
    "2303.TW",
    "2409.TW",
    "2313.TW",
    "3037.TW",
]

st.subheader("今日觀察清單")

for s in stocks:
    st.write("📈", s)
