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


if uploaded_file:

    df = pd.read_excel(uploaded_file, header=4)

    df["KODE_UNIK"] = df["Uraian Transaksi"].apply(ambil_kode_unik)

    database = df[["ID", "KODE_UNIK", "Uraian Transaksi"]]

    database["ID"] = pd.to_numeric(database["ID"], errors="coerce")

    valid = database[database["KODE_UNIK"] != "N/A"]
    anomali = database[database["KODE_UNIK"] == "N/A"]

    valid = valid.drop_duplicates(subset=["ID","KODE_UNIK"])
    valid = valid.sort_values("ID")

    hasil = pd.concat([valid, anomali])

    st.success("Database berhasil dibuat!")

    st.dataframe(hasil)

    output = BytesIO()
    hasil.to_excel(output, index=False)

    st.download_button(
        label="Download DATABASE_HASIL.xlsx",
        data=output.getvalue(),
        file_name="DATABASE_HASIL.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )