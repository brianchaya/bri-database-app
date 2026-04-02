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

            if any("uraian" in str(x) or "description" in str(x) for x in row):
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

    db["ID"] = db["ID"].astype(str)

    db["ID"] = db["ID"].apply(
        lambda x: "N/A" if str(x).strip() == "" or str(x).lower() in ["nan", "none", "nat"]
        else str(x).strip()
    )

    return db

# ==============================
# 🔥 FIXED FILTER NEW ONLY
# ==============================
def filter_new_only(existing, new):

    existing = existing.copy()
    new = new.copy()

    # explode existing
    def explode_existing(df):
        rows = []
        for _, row in df.iterrows():
            ids = str(row["ID"]).split(";")
            for i in ids:
                i = i.strip()
                if i != "":
                    rows.append({
                        "ID": i,
                        "KODE_UNIK": row["KODE_UNIK"],
                        "Description": row["Description"]
                    })
        return pd.DataFrame(rows)

    existing = explode_existing(existing)

    # clean
    def is_numeric(x):
        return str(x).strip().isdigit()

    existing.loc[~existing["ID"].apply(is_numeric), "KODE_UNIK"] = "N/A"
    new.loc[~new["ID"].apply(is_numeric), "KODE_UNIK"] = "N/A"

    existing["KODE_UNIK"] = existing["KODE_UNIK"].apply(normalize_kode)
    new["KODE_UNIK"] = new["KODE_UNIK"].apply(normalize_kode)

    existing["Description"] = existing["Description"].astype(str).str.strip().str.upper()
    new["Description"] = new["Description"].astype(str).str.strip().str.upper()

    existing = existing.drop_duplicates(subset=["ID","KODE_UNIK","Description"])

    # 🔥 DETECT DOUBLE ID (MULTI KODE)
    id_to_kodes = {}
    for _, row in existing.iterrows():
        id_val = str(row["ID"]).strip()
        kode = str(row["KODE_UNIK"]).strip()

        if id_val not in id_to_kodes:
            id_to_kodes[id_val] = set()

        id_to_kodes[id_val].add(kode)

    double_id_set = set(k for k,v in id_to_kodes.items() if len(v) > 1)

    existing_pairs = set(
        existing.loc[existing["KODE_UNIK"] != "N/A"]
        .apply(lambda x: f"{x['KODE_UNIK']}||{x['ID']}", axis=1)
    )

    new_valid = new[new["KODE_UNIK"] != "N/A"].copy()

    # 🔥 BLOCK hanya ID yg sudah multi kode
    new_valid = new_valid[
        ~new_valid["ID"].astype(str).isin(double_id_set)
    ]

    new_valid["PAIR"] = new_valid.apply(
        lambda x: f"{x['KODE_UNIK']}||{x['ID']}", axis=1
    )

    new_valid = new_valid[
        ~new_valid["PAIR"].isin(existing_pairs)
    ]

    new_valid = new_valid.drop(columns=["PAIR"])

    existing_na_desc = set(
        existing.loc[existing["KODE_UNIK"] == "N/A", "Description"]
    )

    new_na = new[new["KODE_UNIK"] == "N/A"]

    new_na = new_na[
        ~new_na["Description"].isin(existing_na_desc)
    ]

    final = pd.concat([new_valid, new_na], ignore_index=True)
    final = final.drop_duplicates(subset=["ID","KODE_UNIK","Description"])

    return final
