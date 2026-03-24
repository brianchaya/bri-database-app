import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.title("BRI Transaction Database Generator (Final v5 - Clean System)")

# ==============================
# UPLOAD
# ==============================
uploaded_file = st.file_uploader("Upload Bank Statement", type=["xlsx","xls","csv"])
existing_file = st.file_uploader("Attach Existing Database (Optional)", type=["xlsx"])

# ==============================
# NORMALIZE KODE
# ==============================
def normalize_kode(x):
    x = str(x).strip().upper()

    if x.startswith("N/A"):
        return "N/A"

    x = re.sub(r'\s+', ' ', x)

    return x

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

    if df is None or df.empty:
        st.error("File could not be read properly.")
        st.stop()

    df.columns = df.columns.astype(str).str.strip()

    id_cols = [c for c in df.columns if c.strip().upper() == "ID"]
    if len(id_cols) == 0:
        st.error("Column 'ID' not found.")
        st.stop()

    id_col = id_cols[0]

    desc_candidates = [
        c for c in df.columns
        if "uraian" in c.lower() or "description" in c.lower()
    ]

    if len(desc_candidates) == 0:
        st.error("Description column not found.")
        st.stop()

    desc_col = desc_candidates[0]

    df["KODE_UNIK"] = df[desc_col].apply(extract_code)
    df["KODE_UNIK"] = df["KODE_UNIK"].apply(normalize_kode)

    db = df[[id_col, "KODE_UNIK", desc_col]].copy()
    db.columns = ["ID", "KODE_UNIK", "Description"]

    db["ID"] = db["ID"].astype(str)

    return db

# ==============================
# FILTER NEW ONLY (SMART)
# ==============================
def filter_new_only(existing, new):

    existing["KODE_UNIK"] = existing["KODE_UNIK"].apply(normalize_kode)

    existing_valid = existing[existing["KODE_UNIK"] != "N/A"]
    existing_codes = set(existing_valid["KODE_UNIK"])

    new_valid = new[new["KODE_UNIK"] != "N/A"]
    filtered_valid = new_valid[
        ~new_valid["KODE_UNIK"].isin(existing_codes)
    ]

    new_na = new[new["KODE_UNIK"] == "N/A"]

    return pd.concat([filtered_valid, new_na], ignore_index=True)

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

    # PISAHKAN N/A
    na = db[db["KODE_UNIK"] == "N/A"].copy()
    na["TYPE"] = "NA"

    db_valid = db[db["KODE_UNIK"] != "N/A"].copy()

    grouped = db_valid.groupby("KODE_UNIK").agg({
        "ID": clean_ids,
        "Description": lambda x: " ; ".join(x.astype(str))
    }).reset_index()

    grouped["TYPE"] = grouped["ID"].apply(
        lambda x: "DOUBLE" if ";" in x else "NORMAL"
    )

    normal = grouped[grouped["TYPE"] == "NORMAL"]
    double = grouped[grouped["TYPE"] == "DOUBLE"]

    return normal, double, na

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

        exist_df = exist_df[["ID", "KODE_UNIK", "DESCRIPTION"]]
        exist_df.columns = ["ID", "KODE_UNIK", "Description"]

        exist_df["TYPE"] = "EXISTING"
        exist_df["KODE_UNIK"] = exist_df["KODE_UNIK"].apply(normalize_kode)

        # FILTER
        filtered_new = filter_new_only(exist_df, new_db)

        if filtered_new.empty:
            st.warning("No new data found.")
            new_final = pd.DataFrame(columns=["ID","KODE_UNIK","Description","TYPE"])
            n_normal = n_double = n_na = pd.DataFrame()
        else:
            n_normal, n_double, n_na = grouping(filtered_new)
            new_final = pd.concat([n_normal, n_double, n_na], ignore_index=True)

        # DASHBOARD
        col1, col2, col3 = st.columns(3)
        col1.metric("New Normal", len(n_normal))
        col2.metric("New Merged", len(n_double))
        col3.metric("New NA", len(n_na))

        # FORMAT OUTPUT
        spacer = pd.DataFrame({
            "ID": ["", ""],
            "KODE_UNIK": ["", ""],
            "Description": ["", ""],
            "TYPE": ["", ""]
        })

        separator = pd.DataFrame({
            "ID": ["--- NEW DATA ---"],
            "KODE_UNIK": [""],
            "Description": [""],
            "TYPE": [""]
        })

        final = pd.concat([
            exist_df,
            spacer,
            separator,
            new_final
        ], ignore_index=True)

        st.success("Mode: UPDATE DATABASE (Clean Append)")

    else:

        normal, double, na = grouping(new_db)

        col1, col2, col3 = st.columns(3)
        col1.metric("Normal Rows", len(normal))
        col2.metric("Merged Rows", len(double))
        col3.metric("Need Review (N/A)", len(na))

        normal = normal.sort_values(by="ID")
        double = double.sort_values(by="ID")

        final = pd.concat([normal, double, na], ignore_index=True)

        st.success("Mode: CREATE NEW DATABASE")

    # SHOW
    st.dataframe(final)

    # EXPORT
    output = BytesIO()

    try:
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            final.to_excel(writer, index=False)
    except:
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            final.to_excel(writer, index=False)

    st.download_button(
        "Download Excel",
        output.getvalue(),
        "DATABASE_FINAL.xlsx"
    )
