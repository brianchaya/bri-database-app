import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.title("BRI Transaction Database Generator")

uploaded_file = st.file_uploader("Upload File Excel", type=["xlsx"])


def ambil_kode_unik(text):

    if pd.isna(text):
        return "N/A"

    text = str(text)

    m = re.search(r'BFVA11167000(\d{5})', text)
    if m:
        return m.group(1)

    m = re.search(r'BRIVA11167000(\d{5})', text)
    if m:
        return m.group(1)

    m = re.search(r'NBMB\s(.*?)\sTO', text)
    if m:
        return m.group(1).strip()

    m = re.search(r'301([A-Z\s]+?):', text)
    if m:
        return m.group(1).strip()

    for i in range(10):
        m = re.search(fr'ATM{i} ATM{i} (.*?)  TO', text)
        if m:
            return m.group(1).strip()

    m = re.search(r'FROM (.*?) LA', text)
    if m:
        return m.group(1).strip()

    m = re.search(r'FROM (.*?) ATM', text)
    if m:
        return m.group(1).strip()

    return "N/A"


def detect_header(file):

    preview = pd.read_excel(file, header=None, nrows=20)

    for i in range(20):
        row = preview.iloc[i].astype(str).str.lower()

        if any("uraian" in cell for cell in row):
            return i

    return 0


def detect_columns(df):

    df.columns = df.columns.str.strip()

    uraian_col = None
    id_col = None

    for col in df.columns:

        if "uraian" in col.lower():
            uraian_col = col

        if col.lower() == "id":
            id_col = col

    return id_col, uraian_col


if uploaded_file:

    header_row = detect_header(uploaded_file)

    df = pd.read_excel(uploaded_file, header=header_row)

    id_col, uraian_col = detect_columns(df)

    if uraian_col is None:
        st.error("Kolom Uraian Transaksi tidak ditemukan.")
        st.write("Kolom yang tersedia:", df.columns)
        st.stop()

    if id_col is None:
        st.error("Kolom ID tidak ditemukan.")
        st.write("Kolom yang tersedia:", df.columns)
        st.stop()

    df["KODE_UNIK"] = df[uraian_col].apply(ambil_kode_unik)

    database = df[[id_col, "KODE_UNIK", uraian_col]]

    database[id_col] = pd.to_numeric(database[id_col], errors="coerce")

    valid = database[database["KODE_UNIK"] != "N/A"]
    anomali = database[database["KODE_UNIK"] == "N/A"]

    valid = valid.drop_duplicates(subset=[id_col, "KODE_UNIK"])

    valid = valid.sort_values(id_col)

    hasil = pd.concat([valid, anomali]).reset_index(drop=True)

    st.success("Database berhasil dibuat")

    st.write("Jumlah transaksi N/A:", len(anomali))

    st.dataframe(hasil)

    output = BytesIO()
    hasil.to_excel(output, index=False)

    st.download_button(
        "Download DATABASE_HASIL.xlsx",
        output.getvalue(),
        "DATABASE_HASIL.xlsx"
    )