import pandas as pd
import streamlit as st
from io import BytesIO

st.set_page_config(page_title="Graded Viewer", page_icon="📝", layout="wide")

st.title("Просмотр оценённых работ 📝")

uploaded = st.file_uploader("Перетащите файл *_graded.xlsx*", type=["xlsx","xls","csv"], accept_multiple_files=False)

if uploaded is None:
    st.info("⬆️ Загрузите файл, чтобы начать.")
    st.stop()

@st.cache_data
def load_df(buf: BytesIO, name: str):
    if name.endswith("csv"):
        return pd.read_csv(buf)
    return pd.read_excel(buf)

df = load_df(uploaded, uploaded.name)

if "Файл" not in df.columns:
    st.error("Не найден столбец 'Файл' — проверьте формат таблицы!")
    st.stop()

files = sorted(df["Файл"].unique())
sel_file = st.sidebar.selectbox("Выберите работу", files)
work_df = df[df["Файл"] == sel_file].reset_index(drop=True)

st.header(f"Работа: {sel_file}")

q_cols = [c for c in work_df.columns if c.startswith("Вопрос ")]
q_cols.sort(key=lambda s:int(s.split()[1]))

for q_col in q_cols:
    idx = q_col.split()[1]
    a_col = f"Ответ {idx}"
    sc_col = f"Оценка {idx}"
    cm_col = f"Комментарий {idx}"

    q = str(work_df.at[0,q_col])
    a = str(work_df.at[0,a_col])
    sc = work_df.at[0,sc_col] if sc_col in work_df else "—"
    cm = work_df.at[0,cm_col] if cm_col in work_df else "—"

    with st.expander(f"Вопрос {idx} • Балл: {sc}", expanded=False):
        st.markdown("**Вопрос**")
        st.markdown(q)
        st.markdown("---")
        st.markdown("**Ответ студента**")
        st.markdown(a)
        st.markdown("---")
        st.markdown("**Комментарий**")
        st.info(str(cm))
