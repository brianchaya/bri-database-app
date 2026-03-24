import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.title("BRI Transaction Database Generator (Stable Final)")

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
# LOAD STATEMENT (MULTI SHEET + HEADER DETECT)
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
# PREPARE NEW DATA (STRICT ID)
# ==============================
def prepare_new(df):

    if df is None or df.empty:
        st.error("File could not be read properly.")
        st.stop()

    df.columns = df.columns.astype(str).str.strip()

    # STRICT ID ONLY
    id_cols = [c for c in df.columns if c.strip().upper() == "ID"]

    if len(id_cols) == 0:
        st.error("Column 'ID' not found (must be exact 'ID').")
        st.write("Detected columns:", list(df.columns))
        st.stop()

    id_col = id_cols[0]

    # DESCRIPTION
    desc_candidates = [
        c for c in df.columns
        if "uraian" in c.lower() or "description" in c.lower()
    ]

    if len(desc_candidates) == 0:
        st.error("Description column not found.")
        st.write("Detected columns:", list(df.columns))
        st.stop()

    desc_col = desc_candidates[0]

    df["KODE_UNIK"] = df[desc_col].apply(extract_code)

    db = df[[id_col, "KODE_UNIK", desc_col]].copy()
    db.columns = ["ID", "KODE_UNIK", "Description"]

    db["ID"] = pd.to_numeric(db["ID"], errors="coerce")

    return db

# ==============================
# GROUPING LOGIC
# ==============================
def grouping(db):

    db = db.drop_duplicates(subset=["ID","KODE_UNIK","Description"])

    db = db[~((db["KODE_UNIK"]=="N/A") & (db["Description"].isna()))]

   grouped = db.groupby("KODE_UNIK").agg({
    "ID": lambda x: " ; ".join(
        sorted(
            set(
                str(i).strip()
                for val in x.dropna()
                for i in str(val).split(";")
                if i.strip().isdigit()
            )
        )
    ),
    "Description": lambda x: " ; ".join(x.astype(str))
}).reset_index()": lambda x: " ; ".join(x.astype(str))
    }).reset_index()

    grouped["TYPE"] = grouped["ID"].apply(lambda x: "DOUBLE" if ";" in x else "NORMAL")

    na = db[db["KODE_UNIK"]=="N/A"].copy()
    na["TYPE"] = "NA"

    normal = grouped[grouped["TYPE"]=="NORMAL"]
    double = grouped[grouped["TYPE"]=="DOUBLE"]

    return normal, double, na

# ==============================
# MERGE EXISTING + NEW
# ==============================
def merge_db(existing, new):

    combined = pd.concat([existing, new], ignore_index=True)

    return grouping(combined)

# ==============================
# MAIN
# ==============================
if uploaded_file:

    df = load_statement(uploaded_file)
    new_db = prepare_new(df)

    if existing_file:

        exist_df = load_existing(existing_file)

        exist_df.columns = [c.upper() for c in exist_df.columns]

        if "DESCRIPTION" not in exist_df.columns:
            exist_df["DESCRIPTION"] = ""

        exist_df = exist_df[["ID","KODE_UNIK","DESCRIPTION"]]
        exist_df.columns = ["ID","KODE_UNIK","Description"]

        normal, double, na = merge_db(exist_df, new_db)

        st.success("Mode: UPDATE DATABASE")

    else:

        normal, double, na = grouping(new_db)

        st.success("Mode: CREATE NEW DATABASE")

    # ==============================
    # DASHBOARD
    # ==============================
    col1, col2, col3 = st.columns(3)

    col1.metric("Normal Rows", len(normal))
    col2.metric("Merged Rows", len(double))
    col3.metric("Need Review (N/A)", len(na))

    # ==============================
    # FINAL TABLE
    # ==============================
    normal = normal.sort_values(by="ID")
    double = double.sort_values(by="ID")

    final = pd.concat([normal, double, na], ignore_index=True)

    st.dataframe(final)

    # ==============================
    # EXPORT (NO XLSXWRITER ERROR)
    # ==============================
    output = BytesIO()

    try:
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            final.to_excel(writer, index=False)

    except:
        # fallback (no color but safe)
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            final.to_excel(writer, index=False)

    st.download_button(
        "Download Excel",
        output.getvalue(),
        "DATABASE_FINAL.xlsx"
    )
