import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.title("BRI Transaction Database Generator (Advanced)")

# ==============================
# UPLOAD FILES
# ==============================
uploaded_file = st.file_uploader("Upload Rekening Koran", type=["xlsx","xls","csv"])
existing_file = st.file_uploader("Attach Existing Database (Optional)", type=["xlsx"])

# ==============================
# EXTRACT UNIQUE CODE
# ==============================
def ambil_kode_unik(text):

    if pd.isna(text):
        return "N/A"

    text = str(text)

    patterns = [
        r'BFVA11167000(\d{5})',
        r'BRIVA11167000(\d{5})',
        r'NBMB\s(.*?)\sTO',
        r'301([A-Z\s]+?):',
        r'ATM\d ATM\d (.*?)  TO',
        r'FROM (.*?) LA',
        r'FROM (.*?) ATM'
    ]

    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(1).strip()

    return "N/A"

# ==============================
# LOAD MULTI SHEET
# ==============================
def load_file(file):

    if file.name.endswith(".csv"):
        return pd.read_csv(file)

    xls = pd.ExcelFile(file)

    for i in range(min(10, len(xls.sheet_names))):
        df = pd.read_excel(xls, sheet_name=i)

        cols = [str(c).lower() for c in df.columns]

        if any("uraian" in c for c in cols) and "id" in cols:
            return df

    return None

# ==============================
# CLEAN & PREP
# ==============================
def prepare_database(df):

    df.columns = df.columns.str.strip()

    uraian_col = [c for c in df.columns if "uraian" in c.lower()][0]
    id_col = [c for c in df.columns if c.lower() == "id"][0]

    df["KODE_UNIK"] = df[uraian_col].apply(ambil_kode_unik)

    db = df[[id_col, "KODE_UNIK", uraian_col]].copy()
    db.columns = ["ID", "KODE_UNIK", "Uraian"]

    db["ID"] = pd.to_numeric(db["ID"], errors="coerce")

    return db

# ==============================
# GROUPING LOGIC
# ==============================
def grouping(db):

    db = db.drop_duplicates(subset=["ID","KODE_UNIK","Uraian"])

    # remove empty N/A
    db = db[~((db["KODE_UNIK"]=="N/A") & (db["Uraian"].isna()))]

    # ==================
    # GROUP DOUBLE
    # ==================
    grouped = db.groupby("KODE_UNIK").agg({
        "ID": lambda x: " ; ".join(sorted(set(x.astype(str)))),
        "Uraian": lambda x: " ; ".join(x.astype(str))
    }).reset_index()

    # detect double
    grouped["TYPE"] = grouped["ID"].apply(lambda x: "DOUBLE" if ";" in x else "NORMAL")

    # ==================
    # N/A
    # ==================
    na = db[db["KODE_UNIK"]=="N/A"].copy()
    na["TYPE"] = "NA"

    # ==================
    # FINAL SPLIT
    # ==================
    normal = grouped[grouped["TYPE"]=="NORMAL"]
    double = grouped[grouped["TYPE"]=="DOUBLE"]

    return normal, double, na

# ==============================
# MERGE EXISTING
# ==============================
def merge_existing(existing, new):

    combined = pd.concat([existing, new], ignore_index=True)

    normal, double, na = grouping(combined)

    return normal, double, na

# ==============================
# MAIN PROCESS
# ==============================
if uploaded_file:

    df = load_file(uploaded_file)

    if df is None:
        st.error("Format tidak dikenali")
        st.stop()

    db = prepare_database(df)

    # ==============================
    # HANDLE EXISTING
    # ==============================
    if existing_file:

        df_exist = load_file(existing_file)
        db_exist = prepare_database(df_exist)

        normal, double, na = merge_existing(db_exist, db)

        st.info("Mode: UPDATE DATABASE")

    else:

        normal, double, na = grouping(db)

        st.info("Mode: CREATE DATABASE BARU")

    # ==============================
    # DASHBOARD
    # ==============================
    col1, col2, col3 = st.columns(3)

    col1.metric("Normal", len(normal))
    col2.metric("Double", len(double))
    col3.metric("N/A", len(na))

    # ==============================
    # DISPLAY
    # ==============================
    st.subheader("DATA")

    final = pd.concat([normal, double, na], ignore_index=True)

    st.dataframe(final)

    # ==============================
    # EXPORT EXCEL WITH COLOR
    # ==============================
    output = BytesIO()

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:

        final.to_excel(writer, index=False, sheet_name="Database")

        workbook = writer.book
        worksheet = writer.sheets["Database"]

        yellow = workbook.add_format({'bg_color': '#FFF59D'})
        red = workbook.add_format({'bg_color': '#EF9A9A'})

        for i, row in final.iterrows():

            if row["KODE_UNIK"] == "N/A":
                worksheet.set_row(i+1, None, red)

            elif ";" in str(row["ID"]):
                worksheet.set_row(i+1, None, yellow)

    st.download_button(
        "Download Excel",
        output.getvalue(),
        "DATABASE_FINAL.xlsx"
    )
