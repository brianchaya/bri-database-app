import streamlit as st
import pandas as pd
import re
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import PatternFill

st.title("BRI Transaction Database Generator")

rk_file = st.file_uploader("Upload Rekening Koran", type=["xlsx","xls","csv"])
existing_db_file = st.file_uploader("Upload Existing Database (optional)", type=["xlsx"])


# ==============================
# BRI UNIQUE CODE EXTRACTOR
# ==============================
def ambil_kode_unik(text):

    if pd.isna(text):
        return "N/A"

    text = str(text).upper()

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


# ==============================
# DETECT SHEET
# ==============================
def detect_sheet(excel):

    for sheet in excel.sheet_names[:10]:

        df = pd.read_excel(excel, sheet_name=sheet, nrows=20)

        text = df.astype(str).to_string().upper()

        if any(x in text for x in ["NBMB","BRIVA","BFVA","ATM","FROM"]):
            return sheet

    return excel.sheet_names[0]


# ==============================
# DETECT HEADER
# ==============================
def detect_header(excel, sheet):

    preview = pd.read_excel(excel, sheet_name=sheet, header=None, nrows=20)

    for i in range(20):

        row = preview.iloc[i].astype(str).str.lower()

        if any(x in row.values for x in ["id","no","ref"]):
            return i

    return 0


# ==============================
# DETECT ID COLUMN
# ==============================
def detect_id_column(df):

    for col in df.columns:

        name = str(col).lower()

        if name in ["id","no","no.","ref","reference"]:
            return col

    numeric_scores = {}

    for col in df.columns:

        series = pd.to_numeric(df[col], errors="coerce")

        numeric_scores[col] = series.nunique()

    return max(numeric_scores, key=numeric_scores.get)


# ==============================
# DETECT TRANSACTION COLUMN
# ==============================
def detect_desc_column(df):

    scores = {}

    for col in df.columns:

        sample = df[col].astype(str).head(200).str.upper()

        score = (
            sample.str.contains("NBMB").sum() +
            sample.str.contains("BRIVA").sum() +
            sample.str.contains("BFVA").sum() +
            sample.str.contains("ATM").sum() +
            sample.str.contains("FROM").sum()
        )

        scores[col] = score

    return max(scores, key=scores.get)


# ==============================
# GROUP CONFLICT
# ==============================
def group_conflict(df):

    normal = []
    conflict = []

    grouped = df.groupby("KODE_UNIK")

    for kode, group in grouped:

        ids = sorted(group["ID"].unique())
        uraian = group["Uraian Transaksi"].tolist()

        if len(ids) == 1:

            normal.append({
                "ID": ids[0],
                "KODE_UNIK": kode,
                "Uraian Transaksi": uraian[0]
            })

        else:

            conflict.append({
                "ID": " ; ".join(map(str,ids)),
                "KODE_UNIK": kode,
                "Uraian Transaksi": " ; ".join(uraian)
            })

    return pd.DataFrame(normal), pd.DataFrame(conflict)


# ==============================
# MAIN PROCESS
# ==============================
if rk_file:

    try:

        if rk_file.name.endswith(".csv"):

            df = pd.read_csv(rk_file)

        else:

            excel = pd.ExcelFile(rk_file)

            sheet = detect_sheet(excel)

            header = detect_header(excel, sheet)

            df = pd.read_excel(excel, sheet_name=sheet, header=header)

        df.columns = df.columns.str.strip()

        id_col = detect_id_column(df)

        desc_col = detect_desc_column(df)

        st.write("Kolom ID terdeteksi:", id_col)
        st.write("Kolom transaksi terdeteksi:", desc_col)

        df["KODE_UNIK"] = df[desc_col].apply(ambil_kode_unik)

        database = df[[id_col,"KODE_UNIK",desc_col]].copy()

        database.columns = ["ID","KODE_UNIK","Uraian Transaksi"]

        database["ID"] = pd.to_numeric(database["ID"], errors="coerce")

        database = database.dropna(subset=["ID"])

        valid = database[database["KODE_UNIK"]!="N/A"]
        na_data = database[database["KODE_UNIK"]=="N/A"]

        valid = valid.drop_duplicates(subset=["ID","KODE_UNIK"])

        normal, conflict = group_conflict(valid)

        col1,col2,col3 = st.columns(3)

        col1.metric("Data normal",len(normal))
        col2.metric("Data konflik",len(conflict))
        col3.metric("N/A",len(na_data))

        wb = Workbook()
        ws = wb.active

        ws.append(["ID","KODE_UNIK","Uraian Transaksi"])

        yellow = PatternFill(start_color="FFFF00",fill_type="solid")
        red = PatternFill(start_color="FF9999",fill_type="solid")

        for _,row in normal.iterrows():
            ws.append(row.tolist())

        for _,row in conflict.iterrows():
            ws.append(row.tolist())
            for c in ws[ws.max_row]:
                c.fill = yellow

        for _,row in na_data.iterrows():
            ws.append(row.tolist())
            for c in ws[ws.max_row]:
                c.fill = red

        output = BytesIO()
        wb.save(output)

        st.download_button(
            "Download DATABASE_BRI.xlsx",
            output.getvalue(),
            "DATABASE_BRI.xlsx"
        )

    except Exception as e:

        st.error("Terjadi error saat memproses file")
        st.write(e)
