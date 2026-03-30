import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.title("BRI Transaction Database Generator")

# ==============================
# UPLOAD
# ==============================
uploaded_file = st.file_uploader("Upload Bank Statement", type=["xlsx","xls","csv"])
existing_file = st.file_uploader("Attach Existing Database (Optional)", type=["xlsx"])

# ==============================
# NORMALIZE KODE (SUPER STRONG)
# ==============================
def normalize_kode(x):
    x = str(x).strip().upper()

    clean = re.sub(r'[^A-Z0-9]', '', x)

    if re.match(r'^N+A*$', clean) or re.match(r'^NA\d*$', clean):
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
# SPLIT EXISTING & OLD NEW
# ==============================
def split_existing_and_new(df):

    df = df.copy()

    marker_idx = df[
        df["ID"].astype(str).str.contains("--- NEW DATA ---", na=False)
    ].index

    if len(marker_idx) == 0:
        return df, pd.DataFrame(columns=df.columns)

    split_idx = marker_idx[0]

    existing = df.iloc[:split_idx].copy()
    new_old = df.iloc[split_idx+1:].copy()

    existing = existing[existing["ID"] != ""]
    new_old = new_old[new_old["ID"] != ""]

    return existing, new_old

# ==============================
# MERGE EXISTING + OLD NEW
# ==============================
def merge_existing_with_old_new(existing, old_new):

    if old_new is None or old_new.empty:
        return existing

    combined = pd.concat([existing, old_new], ignore_index=True)

    normal, double, na = grouping(combined)

    merged = pd.concat([normal, double, na], ignore_index=True)

    def get_min_id(x):
        nums = re.findall(r'\d+', str(x))
        return int(nums[0]) if nums else 999999999

    merged["SORT_KEY"] = merged["ID"].apply(get_min_id)
    merged = merged.sort_values("SORT_KEY").drop(columns="SORT_KEY")

    return merged

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

    db["ID"] = db["ID"].astype(str).replace(
        ["nan", "None", "NaT", ""], "N/A"
    )

    return db

# ==============================
# FILTER NEW ONLY (NO N/A)
# ==============================
def filter_new_only(existing, new):

    existing["KODE_UNIK"] = existing["KODE_UNIK"].apply(normalize_kode)
    new["KODE_UNIK"] = new["KODE_UNIK"].apply(normalize_kode)

    existing_codes = set(
        existing[existing["KODE_UNIK"] != "N/A"]["KODE_UNIK"]
    )

    new_valid = new[new["KODE_UNIK"] != "N/A"]
    new_na = new[new["KODE_UNIK"] == "N/A"]

    new_valid = new_valid[
        ~new_valid["KODE_UNIK"].isin(existing_codes)
    ]

    existing_na_desc = set(
        existing[existing["KODE_UNIK"] == "N/A"]["Description"]
    )

    new_na = new_na[
        ~new_na["Description"].isin(existing_na_desc)
    ]

    filtered = pd.concat([new_valid, new_na], ignore_index=True)

    return filtered

# ==============================
# CLEAN ID (FIX 🔥)
# ==============================
def clean_ids(x):

    ids = []

    for val in x.dropna():
        parts = str(val).split(";")

        for p in parts:
            p = p.strip()
            if p:
                ids.append(p)

    return " ; ".join(sorted(set(ids))) if ids else "N/A"

# ==============================
# VALIDATE NUMERIC ID (NEW 🔥)
# ==============================
def is_pure_numeric_id(x):
    x = str(x).strip()
    return bool(re.fullmatch(r'\d+', x))

# ==============================
# GROUPING
# ==============================
def grouping(db):

    db = db.copy()
    db["KODE_UNIK"] = db["KODE_UNIK"].apply(normalize_kode)
    db["ID"] = db["ID"].astype(str)

    # 🔥 FIX DI SINI
    db_na = db[
        (db["KODE_UNIK"] == "N/A") |
        (db["ID"].str.upper() == "N/A") |
        (~db["ID"].apply(is_pure_numeric_id))
    ].copy()

    db_valid = db[
        (db["KODE_UNIK"] != "N/A") &
        (db["ID"].str.upper() != "N/A") &
        (db["ID"].apply(is_pure_numeric_id))
    ].copy()

    db_valid = db_valid.drop_duplicates(subset=["ID", "KODE_UNIK", "Description"])

    id_group = db_valid.groupby("ID")["KODE_UNIK"].nunique().reset_index()
    multi_kode_ids = set(id_group[id_group["KODE_UNIK"] > 1]["ID"])

    db_valid["FORCE_DOUBLE"] = db_valid["ID"].apply(lambda x: x in multi_kode_ids)

    normal_base = db_valid[~db_valid["FORCE_DOUBLE"]]

    grouped_normal = normal_base.groupby("KODE_UNIK").agg({
        "ID": clean_ids,
        "Description": lambda x: " ; ".join(x.astype(str))
    }).reset_index()

    grouped_normal["TYPE"] = "NORMAL"

    kode_group = db_valid.groupby("KODE_UNIK")["ID"].nunique().reset_index()
    multi_id_kode = set(kode_group[kode_group["ID"] > 1]["KODE_UNIK"])

    double_kode = db_valid[db_valid["KODE_UNIK"].isin(multi_id_kode)]

    grouped_double_kode = double_kode.groupby("KODE_UNIK").agg({
        "ID": clean_ids,
        "Description": lambda x: " ; ".join(x.astype(str))
    }).reset_index()

    grouped_double_kode["TYPE"] = "DOUBLE"

    double_id = db_valid[db_valid["FORCE_DOUBLE"]]

    grouped_double_id = double_id.groupby("ID").agg({
        "KODE_UNIK": lambda x: " ; ".join(sorted(set(x))),
        "Description": lambda x: " ; ".join(x.astype(str))
    }).reset_index()

    grouped_double_id["TYPE"] = "DOUBLE"

    db_na = db_na.drop_duplicates(subset=["Description"])
    db_na["TYPE"] = "NA"

    normal = grouped_normal
    double = pd.concat([grouped_double_kode, grouped_double_id], ignore_index=True)

    return normal, double, db_na

# ==============================
# SORT
# ==============================
def sort_by_id(df):

    def get_min_id(x):
        nums = re.findall(r'\d+', str(x))
        return min([int(n) for n in nums]) if nums else 999999999

    df = df.copy()

    df["IS_NA"] = df["KODE_UNIK"].apply(lambda x: 1 if x == "N/A" else 0)
    df["SORT_KEY"] = df["ID"].apply(get_min_id)

    df = df.sort_values(["IS_NA", "SORT_KEY"]).drop(columns=["SORT_KEY", "IS_NA"])

    return df
