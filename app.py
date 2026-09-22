import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import os
from pathlib import Path
from datetime import datetime
from io import BytesIO

st.set_page_config(page_title="Staff Diary Request", page_icon="📘", layout="wide")

APP_DIR = Path(__file__).parent
DB_PATH = Path(os.getenv("DIARY_DB_PATH", APP_DIR / "diary_requests.db"))
STAFF_FILE = APP_DIR / "staff.csv"

DIARY_TYPES = [
    "A4 Day-to-Page",
    "A4 Week-to-View",
    "A5 Day-to-Page",
    "A5 Week-to-View",
    "Pocket Diary",
    "No diary required",
    "Other",
]
COLOURS = ["No preference", "Black", "Blue", "Red", "Other"]

def secret(name, default=""):
    try:
        return st.secrets[name]
    except Exception:
        return os.getenv(name, default)

ADMIN_PASSWORD = secret("ADMIN_PASSWORD", "ChangeMe123!")

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def conn():
    c = sqlite3.connect(DB_PATH)
    c.execute("""CREATE TABLE IF NOT EXISTS requests(
        staff_name TEXT PRIMARY KEY,
        department TEXT,
        diary_type TEXT NOT NULL,
        colour TEXT,
        other_details TEXT,
        comments TEXT,
        submitted_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    c.commit()
    return c

def staff_list():
    return pd.read_csv(STAFF_FILE).fillna("").sort_values("staff_name")

def requests():
    c = conn()
    df = pd.read_sql_query("SELECT * FROM requests ORDER BY staff_name", c)
    c.close()
    return df

def save(name, dept, diary, colour, details, comments):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c = conn()
    old = c.execute("SELECT submitted_at FROM requests WHERE staff_name=?", (name,)).fetchone()
    created = old[0] if old else now
    c.execute("""INSERT INTO requests VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(staff_name) DO UPDATE SET
        department=excluded.department, diary_type=excluded.diary_type,
        colour=excluded.colour, other_details=excluded.other_details,
        comments=excluded.comments, updated_at=excluded.updated_at""",
        (name, dept, diary, colour, details, comments, created, now))
    c.commit(); c.close()

def excel_report(req, staff):
    responded = set(req.staff_name) if not req.empty else set()
    outstanding = staff[~staff.staff_name.isin(responded)]
    orderable = req[req.diary_type != "No diary required"] if not req.empty else req
    totals = (orderable.groupby(["diary_type","colour"]).size()
              .reset_index(name="Quantity")) if not orderable.empty else pd.DataFrame(
                  columns=["diary_type","colour","Quantity"])
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
   req.to_excel(w, sheet_name="All Requests", index=False)
totals.to_excel(w, sheet_name="Order Totals", index=False)
outstanding.to_excel(w, sheet_name="Outstanding Staff", index=False)
staff.to_excel(w, sheet_name="Staff List", index=False)
        for ws in w.book.worksheets:
            ws.freeze_panes = "A2"
            for col in ws.columns:
                n=max([len(str(x.value or "")) for x in col] or [10])
                ws.column_dimensions[col[0].column_letter].width=min(max(n+2,12),45)
    out.seek(0); return out

staff = staff_list()
req = requests()

st.title("📘 Staff Diary Request")
st.write("Submit your diary preference below. You can return later and update your selection.")

staff_tab, admin_tab = st.tabs(["Staff Request", "🔒 Admin"])

with staff_tab:
    name = st.selectbox("Your name", ["— Select your name —"] + staff.staff_name.tolist())
    if name != "— Select your name —":
        row = staff[staff.staff_name == name].iloc[0]
        old = req[req.staff_name == name]
        old = old.iloc[0] if not old.empty else None
        if old is not None:
            st.info("A request already exists for you. Submitting again will update it.")

        dept = row.department
        if dept:
            st.text_input("Department", dept, disabled=True)

        old_diary = old.diary_type if old is not None else DIARY_TYPES[0]
        diary = st.radio("Which diary would you like?", DIARY_TYPES,
                         index=DIARY_TYPES.index(old_diary) if old_diary in DIARY_TYPES else 0)

        if diary == "No diary required":
            colour = "N/A"
        else:
            old_colour = old.colour if old is not None else "No preference"
            colour = st.selectbox("Colour preference", COLOURS,
                                  index=COLOURS.index(old_colour) if old_colour in COLOURS else 0)

        details = ""
        if diary == "Other":
            details = st.text_input("Please describe the diary required",
                                    value=(old.other_details if old is not None else ""))
        comments = st.text_area("Additional comments (optional)",
                                value=(old.comments if old is not None else ""))

        if st.button("Submit / Update Request", type="primary", use_container_width=True):
            if diary == "Other" and not details.strip():
                st.warning("Please describe the diary required.")
            else:
                save(name, dept, diary, colour, details.strip(), comments.strip())
                st.success("Thank you. Your diary request has been recorded.")
                st.rerun()

with admin_tab:
    if "admin_ok" not in st.session_state:
        st.session_state.admin_ok = False

    if not st.session_state.admin_ok:
        st.subheader("Admin access")
        pw = st.text_input("Admin password", type="password")
        if st.button("Log in"):
            if hash_pw(pw) == hash_pw(ADMIN_PASSWORD):
                st.session_state.admin_ok = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    else:
        req = requests()
        total = len(staff)
        responses = len(req)
        no_diary = int((req.diary_type == "No diary required").sum()) if not req.empty else 0
        outstanding_n = total - responses

        top1,top2,top3,top4 = st.columns(4)
        top1.metric("Total Staff", total)
        top2.metric("Responses", responses)
        top3.metric("Diaries Required", responses-no_diary)
        top4.metric("Outstanding", outstanding_n)

        st.subheader("Order totals")
        orderable = req[req.diary_type != "No diary required"] if not req.empty else req
        if orderable.empty:
            st.info("No diary orders have been submitted yet.")
        else:
            totals=(orderable.groupby(["diary_type","colour"]).size()
                    .reset_index(name="Quantity")
                    .rename(columns={"diary_type":"Diary Type","colour":"Colour"}))
            st.dataframe(totals, use_container_width=True, hide_index=True)

        st.subheader("All responses")
        if req.empty:
            st.info("No responses yet.")
        else:
            show=req.rename(columns={"staff_name":"Staff Name","department":"Department",
                "diary_type":"Diary Type","colour":"Colour","other_details":"Other Details",
                "comments":"Comments","updated_at":"Last Updated"})
            st.dataframe(show[["Staff Name","Department","Diary Type","Colour",
                               "Other Details","Comments","Last Updated"]],
                         use_container_width=True, hide_index=True)

        st.subheader("Outstanding staff")
        responded=set(req.staff_name) if not req.empty else set()
        outstanding=staff[~staff.staff_name.isin(responded)]
        if outstanding.empty:
            st.success("All staff have responded.")
        else:
            st.dataframe(outstanding, use_container_width=True, hide_index=True)

        st.download_button("Download Excel Report", excel_report(req, staff),
                           file_name=f"diary_requests_{datetime.now():%Y%m%d}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)

        if st.button("Log out"):
            st.session_state.admin_ok=False
            st.rerun()
