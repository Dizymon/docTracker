# Setup & Run

### 1. Install dependencies
```bash
pip install django pillow
```

### 2. Set up the database
```bash
python manage.py migrate
```

### 3. Create an admin user
```bash
python manage.py createsuperuser
```

### 4. Run the server
```bash
python manage.py runserver
```
Open http://127.0.0.1:8000

---


 Username  Password       Role  |
--------------------------------|
 admin     admin123       Admin |
 jane      jane123        User  |
 tristan   tristanramos   Admin |
---

## Features
- **Dashboard** — Stats overview + recent activity
- **Documents** — Create, view, edit, delete documents
  - Status workflow: Draft → Under Review → Approved → Archived
  - File attachments
  - Tags (comma-separated)
  - Due dates
  - Assign to users
- **Categories** — Organize documents by category
- **Comments** — Leave comments on any document
- **History** — Auto-tracked status change history
- **Search & Filter** — Filter by status, category, assigned user, or keyword
- **User accounts** — Register/login/logout

## Project Structure
```
doctracker/
├── doctracker/          # Project config (settings, urls)
├── documents/           # Main app (models, views, forms)
├── templates/           # HTML templates
│   ├── base.html
│   ├── auth/
│   └── documents/
├── media/               # Uploaded files
├── db.sqlite3           # SQLite database
└── manage.py
```
