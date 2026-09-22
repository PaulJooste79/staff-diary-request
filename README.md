# Staff Diary Request – Shared Web Version

This version is designed to be hosted centrally so staff use ONE web link.

## Included
- 13 staff names already loaded
- Staff submit or update their own request
- A4/A5/pocket/no-diary/other options
- Colour preference
- Password-protected Admin tab
- Response and outstanding counts
- Ordering totals
- Excel export

## Test it locally
From this folder:

    py -m pip install -r requirements.txt
    py -m streamlit run app.py

The temporary fallback admin password is:

    ChangeMe123!

Change this before real use.

## Hosting
Upload the project to a Python/Streamlit-capable hosting service and configure:

    ADMIN_PASSWORD = your chosen password

IMPORTANT ABOUT SHARED DATA:
The app uses SQLite by default. This is excellent for local testing, but some cloud hosts use
ephemeral/local files that can be reset when the app restarts or redeploys. For a permanent
production staff system, use a host with persistent disk or replace SQLite with a hosted
database (for example PostgreSQL/Supabase).

Do not rely on a free ephemeral deployment for business records without a backup.

## Staff
Edit staff.csv to add/remove names. Keep the headings:
staff_name,department
