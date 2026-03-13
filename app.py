import pandas as pd
import re


# ===== AUTO DETECT HEADER =====
def detect_header(file):

    preview = pd.read_excel(file, header=None, nrows=20)

    for i in range(20):
        row = preview.iloc[i].astype(str).str.lower()

        if any("uraian" in cell for cell in row):
            return i

    return 0


# ===== AUTO DETECT COLUMN =====
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


# ===== EXTRACT UNIQUE CODE =====
def ambil_kode_unik(text):

    if pd.isna(text):
        return "N/A"

    text = str(text)

    # MODEL 1
    m = re.search(r'BFVA11167000(\d{5})', text)
    if m:
        return m.group(1)

    # MODEL 3
    m = re.search(r'BRIVA11167000(\d{5})', text)
    if m:
        return m.group(1)

    # MODEL 2
    m = re.search(r'NBMB\s(.*?)\sTO', text)
    if m:
        return m.group(1).strip()

    # MODEL 4
    m = re.search(r'301([A-Z\s]+?):', text)
    if m:
        return m.group(1).strip()

    # MODEL 5 ATM0-ATM9
    for i in range(10):
        m = re.search(fr'ATM{i} ATM{i} (.*?)  TO', text)
        if m:
            return m.group(1).strip()

    # MODEL 6
    m = re.search(r'FROM (.*?) LA', text)
    if m:
        return m.group(1).strip()

    # MODEL 7
    m = re.search(r'FROM (.*?) ATM', text)
    if m:
        return m.group(1).strip()

    return "N/A"


# ===== LOAD FILE =====
file = "BRI - Summary FY26.xlsx"

header_row = detect_header(file)

df = pd.read_excel(file, header=header_row)

id_col, uraian_col = detect_columns(df)

if uraian_col is None or id_col is None:
    raise Exception("Kolom ID atau Uraian Transaksi tidak ditemukan")


# ===== LOGIC SAMA PERSIS SEPERTI SCRIPT KAMU =====
df["KODE_UNIK"] = df[uraian_col].apply(ambil_kode_unik)

database = df[[id_col, "KODE_UNIK", uraian_col]]

database = database.rename(columns={
    id_col: "ID",
    uraian_col: "Uraian Transaksi"
})

database["ID"] = pd.to_numeric(database["ID"], errors="coerce")

valid = database[database["KODE_UNIK"] != "N/A"].copy()
anomali = database[database["KODE_UNIK"] == "N/A"].copy()

valid = valid.drop_duplicates(subset=["ID","KODE_UNIK"])

valid = valid.sort_values("ID")

hasil = pd.concat([valid, anomali])

hasil = hasil.reset_index(drop=True)

hasil.to_excel("DATABASE_HASIL.xlsx", index=False)

print("Database selesai dibuat")
print("Jumlah N/A :", len(anomali))
