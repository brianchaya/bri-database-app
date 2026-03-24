import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.title("BRI Transaction Database Generator (Split Mode)")

# ==============================
# UPLOAD
# ==============================
uploaded_file = st.file_uploader("Upload Bank Statement", type=["xlsx","xls","csv"])
existing_file = st.file_uploader("Attach Existing Database (Optional)", type=["xlsx"])

# ==============================
# EXTRACT UNIQUE CODE
# ==============================
def extract_code(text):

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
# LOAD STATEMENT
# ==============================
def load_statement(file):

    if file.name.endswith(".csv"):
        return pd.read_csv(file)

    xls = pd.ExcelFile(file)

    for sheet in xls.sheet_names[:10]:
        preview = pd.read_excel(xls, sheet_name=sheet, header=None, nrows=20)

        for i in range(len(preview)):
            row = preview.iloc[i].astype(str).str.lower()

            if any("uraian" in x or "description" in x for x in row):
                return pd.read_excel(xls, sheet_name=sheet, header=i)

    return pd.read_excel(xls, sheet_name=0)

# ==============================
# LOAD EXISTING
# ==============================
def load_existing(file):

    xls = pd.ExcelFile(file)

    for sheet in xls.sheet_names[:10]:
        df = pd.read_excel(xls, sheet_name=sheet)

        cols = [str(c).upper() for c in df.columns]

        if "ID" in cols and "KODE_UNIK" in cols:
            return df

    return pd.read_excel(xls, sheet_name=0)

# ==============================
# PREPARE NEW DATA
# ==============================
def prepare_new(df):

    df.columns = df.columns.astype(str).str.strip()

    id_cols = [c for c in df.columns if c.strip().upper() == "ID"]
    desc_candidates = [c for c in df.columns if "uraian" in c.lower() or "description" in c.lower()]

    if not id_cols or not desc_candidates:
        st.error("Column ID / Description tidak ditemukan.")
        st.stop()

    id_col = id_cols[0]
    desc_col = desc_candidates[0]

    df["KODE_UNIK"] = df[desc_col].apply(extract_code)

    db = df[[id_col, "KODE_UNIK", desc_col]].copy()
    db.columns = ["ID", "KODE_UNIK", "Description"]

    db["ID"] = db["ID"].astype(str)

    return db

# ==============================
# CLEAN ID
# ==============================
def clean_ids(x):

    ids = []

    for val in x.dropna():
        parts = str(val).split(";")

        for p in parts:
            p = p.strip()
            found = re.findall(r'\d+', p)
            if found:
                ids.extend(found)

    return " ; ".join(sorted(set(ids)))

# ==============================
# GROUPING
# ==============================
def grouping(db):

    db = db.drop_duplicates(subset=["ID", "KODE_UNIK", "Description"])

    grouped = db.groupby("KODE_UNIK").agg({
        "ID": clean_ids,
        "Description": lambda x: " ; ".join(x.astype(str))
    }).reset_index()

    grouped["TYPE"] = grouped["ID"].apply(lambda x: "DOUBLE" if ";" in x else "NORMAL")

    return grouped

# ==============================
# MAIN
# ==============================
if uploaded_file:

    df = load_statement(uploaded_file)
    new_db_raw = prepare_new(df)
    new_grouped = grouping(new_db_raw)

    if existing_file:

        exist_df = load_existing(existing_file)
        exist_df.columns = [c.upper() for c in exist_df.columns]

        if "DESCRIPTION" not in exist_df.columns:
            exist_df["DESCRIPTION"] = ""

        exist_df = exist_df[["ID","KODE_UNIK","DESCRIPTION"]]
        exist_df.columns = ["ID","KODE_UNIK","Description"]

        existing_grouped = grouping(exist_df)

        st.success("Mode: SPLIT DATABASE")

        st.subheader("Existing Database")
        st.dataframe(existing_grouped)

        st.write("")  # jarak
        st.write("")

        st.subheader("New Database")
        st.dataframe(new_grouped)

        # ==============================
        # EXPORT (SPLIT)
        # ==============================
        output = BytesIO()

        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:

            existing_grouped.to_excel(writer, index=False, startrow=0)

            new_grouped.to_excel(
                writer,
                index=False,
                startrow=len(existing_grouped) + 3
            )

        st.download_button(
            "Download Excel",
            output.getvalue(),
            "DATABASE_SPLIT.xlsx"
        )

    else:

        st.success("Mode: CREATE NEW DATABASE")
        st.dataframe(new_grouped)

        output = BytesIO()

        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            new_grouped.to_excel(writer, index=False)

        st.download_button(
            "Download Excel",
            output.getvalue(),
            "DATABASE_NEW.xlsx"
        )
