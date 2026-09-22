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
   responded = set(req["staff_name"]) if not req.empty else set()

    outstanding = staff[
        ~staff["staff_name"].isin(responded)
    ].copy()

    if not req.empty:
        orderable = req[
            req["diary_type"] != "No diary required"
        ].copy()
    else:
        orderable = req.copy()

    if not orderable.empty:
        totals = (
            orderable
            .groupby(["diary_type", "colour"])
            .size()
            .reset_index(name="Quantity")
        )
    else:
        totals = pd.DataFrame(
            columns=["diary_type", "colour", "Quantity"]
        )

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        req.to_excel(
            writer,
            sheet_name="All Requests",
            index=False
        )

        totals.to_excel(
            writer,
            sheet_name="Order Totals",
            index=False
        )

        outstanding.to_excel(
            writer,
            sheet_name="Outstanding Staff",
            index=False
        )

        staff.to_excel(
            writer,
            sheet_name="Staff List",
            index=False
        )

        for worksheet in writer.book.worksheets:
            worksheet.freeze_panes = "A2"

            for column in worksheet.columns:
                max_length = max(
                    len(str(cell.value or ""))
                    for cell in column
                )

                worksheet.column_dimensions[
                    column[0].column_letter
                ].width = min(
                    max(max_length + 2, 12),
                    45
                )

    output.seek(0)
    return output
