import hashlib
import os
import sqlite3
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Staff Diary Request", page_icon="📘", layout="wide")

APP_DIR = Path(__file__).parent
DB_PATH = Path(os.getenv("DIARY_DB_PATH", str(APP_DIR / "diary_requests.db")))
STAFF_FILE = APP_DIR / "staff.csv"

DIARY_TYPES = ["A4 Day-to-Page", "A4 Week-to-View", "A5 Day-to-Page",
               "A5 Week-to-View", "Pocket Diary", "No diary required", "Other"]
COLOURS = ["No preference", "Black", "Blue", "Red", "Other"]

def get_secret(name, default=""):
    try:
        return st.secrets[name]
    except Exception:
        return os.getenv(name, default)

ADMIN_PASSWORD = get_secret("ADMIN_PASSWORD", "ChangeMe123!")

def password_matches(password):
    return hashlib.sha256(password.encode()).hexdigest() == hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()

def get_connection():
    c = sqlite3.connect(DB_PATH)
    c.execute("""CREATE TABLE IF NOT EXISTS requests (
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

def load_staff():
    if not STAFF_FILE.exists():
        st.error("staff.csv could not be found.")
        st.stop()
    df = pd.read_csv(STAFF_FILE).fillna("")
    if not {"staff_name", "department"}.issubset(df.columns):
        st.error("staff.csv must contain staff_name and department columns.")
        st.stop()
    df["staff_name"] = df["staff_name"].astype(str).str.strip()
    df["department"] = df["department"].astype(str).str.strip()
    return df[df["staff_name"] != ""].drop_duplicates("staff_name").sort_values("staff_name").reset_index(drop=True)

def load_requests():
    c = get_connection()
    df = pd.read_sql_query("SELECT * FROM requests ORDER BY staff_name", c)
    c.close()
    return df

def save_request(name, department, diary_type, colour, other_details, comments):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c = get_connection()
    old = c.execute("SELECT submitted_at FROM requests WHERE staff_name=?", (name,)).fetchone()
    submitted_at = old[0] if old else now
    c.execute("""INSERT INTO requests
        (staff_name, department, diary_type, colour, other_details, comments, submitted_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(staff_name) DO UPDATE SET
        department=excluded.department, diary_type=excluded.diary_type,
        colour=excluded.colour, other_details=excluded.other_details,
        comments=excluded.comments, updated_at=excluded.updated_at""",
        (name, department, diary_type, colour, other_details, comments, submitted_at, now))
    c.commit()
    c.close()

def delete_request(name):
    c = get_connection()
    c.execute("DELETE FROM requests WHERE staff_name=?", (name,))
    c.commit()
    c.close()

def build_excel_report(req, staff):
    responded = set(req["staff_name"]) if not req.empty else set()
    outstanding = staff[~staff["staff_name"].isin(responded)].copy()
    orderable = req[req["diary_type"] != "No diary required"].copy() if not req.empty else req.copy()
    if orderable.empty:
        totals = pd.DataFrame(columns=["Diary Type", "Colour", "Quantity"])
    else:
        totals = (orderable.groupby(["diary_type", "colour"], dropna=False).size()
                  .reset_index(name="Quantity")
                  .rename(columns={"diary_type": "Diary Type", "colour": "Colour"}))
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        req.to_excel(writer, sheet_name="All Requests", index=False)
        totals.to_excel(writer, sheet_name="Order Totals", index=False)
        outstanding.to_excel(writer, sheet_name="Outstanding Staff", index=False)
        staff.to_excel(writer, sheet_name="Staff List", index=False)
        for ws in writer.book.worksheets:
            ws.freeze_panes = "A2"
            for col in ws.columns:
                width = max(len(str(cell.value or "")) for cell in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 12), 45)
    output.seek(0)
    return output.getvalue()

staff = load_staff()
req = load_requests()

st.title("📘 Staff Diary Request")
st.write("Submit your diary preference below. You can return later and update your selection.")
staff_tab, admin_tab = st.tabs(["Staff Request", "🔒 Admin"])

with staff_tab:
    name = st.selectbox("Your name", ["— Select your name —"] + staff["staff_name"].tolist())
    if name != "— Select your name —":
        row = staff[staff["staff_name"] == name].iloc[0]
        department = row["department"]
        existing_rows = req[req["staff_name"] == name]
        existing = existing_rows.iloc[0] if not existing_rows.empty else None

        if existing is not None:
            st.info("A request already exists for you. Submitting again will update it.")
        if department:
            st.text_input("Department", value=department, disabled=True)

        old_diary = existing["diary_type"] if existing is not None else DIARY_TYPES[0]
        diary_type = st.radio("Which diary would you like?", DIARY_TYPES,
                              index=DIARY_TYPES.index(old_diary) if old_diary in DIARY_TYPES else 0)

        if diary_type == "No diary required":
            colour = "N/A"
        else:
            old_colour = existing["colour"] if existing is not None else "No preference"
            colour = st.selectbox("Colour preference", COLOURS,
                                  index=COLOURS.index(old_colour) if old_colour in COLOURS else 0)

        other_details = ""
        if diary_type == "Other":
            other_details = st.text_input("Please describe the diary required",
                                          value=existing["other_details"] if existing is not None else "")
        comments = st.text_area("Additional comments (optional)",
                                value=existing["comments"] if existing is not None else "")

        if st.button("Submit / Update Request", type="primary", use_container_width=True):
            if diary_type == "Other" and not other_details.strip():
                st.warning("Please describe the diary required.")
            else:
                save_request(name, department, diary_type, colour, other_details.strip(), comments.strip())
                st.success("Thank you. Your diary request has been recorded.")
                st.rerun()

with admin_tab:
    if "admin_authenticated" not in st.session_state:
        st.session_state.admin_authenticated = False

    if not st.session_state.admin_authenticated:
        st.subheader("Admin access")
        entered = st.text_input("Admin password", type="password")
        if st.button("Log in"):
            if password_matches(entered):
                st.session_state.admin_authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    else:
        req = load_requests()
        total_staff = len(staff)
        response_count = len(req)
        no_diary = int((req["diary_type"] == "No diary required").sum()) if not req.empty else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Staff", total_staff)
        c2.metric("Responses", response_count)
        c3.metric("Diaries Required", response_count - no_diary)
        c4.metric("Outstanding", total_staff - response_count)

        st.subheader("Order totals")
        orderable = req[req["diary_type"] != "No diary required"].copy() if not req.empty else req.copy()
        if orderable.empty:
            st.info("No diary orders have been submitted yet.")
        else:
            totals = (orderable.groupby(["diary_type", "colour"], dropna=False).size()
                      .reset_index(name="Quantity")
                      .rename(columns={"diary_type": "Diary Type", "colour": "Colour"}))
            st.dataframe(totals, use_container_width=True, hide_index=True)

        st.subheader("All responses")
        if req.empty:
            st.info("No responses yet.")
        else:
            display = req.rename(columns={
                "staff_name": "Staff Name", "department": "Department",
                "diary_type": "Diary Type", "colour": "Colour",
                "other_details": "Other Details", "comments": "Comments",
                "updated_at": "Last Updated"
            })
            st.dataframe(display[["Staff Name", "Department", "Diary Type", "Colour",
                                  "Other Details", "Comments", "Last Updated"]],
                         use_container_width=True, hide_index=True)

        st.subheader("Outstanding staff")
        responded = set(req["staff_name"]) if not req.empty else set()
        outstanding = staff[~staff["staff_name"].isin(responded)].copy()
        if outstanding.empty:
            st.success("All staff have responded.")
        else:
            st.dataframe(outstanding, use_container_width=True, hide_index=True)

        report = build_excel_report(req, staff)
        st.download_button("Download Excel Report", data=report,
                           file_name=f"diary_requests_{datetime.now():%Y%m%d}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)

        with st.expander("Admin: remove a response"):
            if req.empty:
                st.write("There are no responses to remove.")
            else:
                remove_name = st.selectbox("Select staff member", req["staff_name"].tolist(),
                                           key="remove_staff")
                if st.button("Remove selected response", key="remove_response"):
                    delete_request(remove_name)
                    st.success(f"Response removed for {remove_name}.")
                    st.rerun()

        if st.button("Log out"):
            st.session_state.admin_authenticated = False
            st.rerun()
