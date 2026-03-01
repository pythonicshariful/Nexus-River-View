# 🏢 Nexus River View

**Nexus River View** is a comprehensive real estate management system built for managing customers, directors, installments, transactions, and bank accounts for housing projects. It features Google Sheets sync, AI chat support, and a full-featured web dashboard.

---

## 📥 Download

> **[⬇️ Download Nexus River View (Latest Release)](https://drive.google.com/file/d/1Y4WQQE1ujk17Ay0ceixJHXTi_wME-pDh/view?usp=sharing)**

Download the `.exe` installer or portable version from the link above. No Python installation required to run the pre-built executable.

---

## ✨ Features

- **Customer Management** — Add, edit, and track customers with full personal details (NID, address, profession, etc.)
- **Director Management** — Manage directors, their share allocations, and financial dues
- **Installment Tracking** — Create installments (e.g., Booking, Piling, Foundation), track paid/due per customer
- **Transaction History** — Record payments with bank name, transaction ID, date, and receipt images
- **Bank Account Management** — Track multiple bank accounts with full transaction ledgers
- **Petty Cash Ledger** — Record income/expense entries with categories
- **Excel Export** — Export detailed customer and financial reports to `.xlsx`
- **Google Sheets Sync** — Two-way sync with Google Sheets for remote access and backup
- **AI Chat Assistant** — Built-in AI assistant powered by Google Gemini
- **Multi-Profile Support** — Switch between multiple project databases seamlessly
- **Auto Backup & Recovery** — Automatic database backup and restore from Google Sheets

---

## 🚀 Getting Started (Running from Source)

### Prerequisites

- Python 3.10+
- pip

### Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd nexus-river-view

# Create a virtual environment (recommended)
python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate   # Linux/macOS

# Install dependencies
pip install -r requirements.txt
```

### Configuration

1. Copy `.env.example` to `.env` and fill in your settings (or edit `.env` directly).
2. Place your `credentials.json` (Google Service Account) in the project root to enable Google Sheets sync.
3. Edit `admin_config.json` to set your admin password (default: `1234`).

### Run

```bash
python app.py
```

Then open your browser and navigate to: **http://127.0.0.1:5000**

---

## 🖥️ Running the Desktop App (GUI)

```bash
python run_gui.py
```

This launches the application in a native desktop window using a built-in WebView wrapper.

---

## 📦 Building the Executable

```bash
python build_exe.py
```

The output `.exe` will be placed in the `dist/` folder.

---

## 🗂️ Project Structure

```
nexus-river-view/
├── app.py              # Flask application factory
├── routes.py           # All API and page routes
├── models.py           # SQLAlchemy database models
├── logic.py            # Core business logic
├── sync_manager.py     # Google Sheets sync
├── ai_chat.py          # AI chat assistant
├── run_gui.py          # Desktop GUI launcher
├── build_exe.py        # PyInstaller build script
├── templates/          # HTML templates
├── static/             # CSS, JS, images
├── instance/           # Database files (auto-created)
└── requirements.txt    # Python dependencies
```

---

## 🛠️ Tech Stack

| Layer       | Technology                        |
|-------------|-----------------------------------|
| Backend     | Python, Flask, SQLAlchemy         |
| Database    | SQLite                            |
| Frontend    | HTML, CSS, JavaScript (Jinja2)    |
| Sync        | Google Sheets API (gspread)       |
| AI          | Google Gemini (google-genai)      |
| Export      | openpyxl, pandas                  |
| Packaging   | PyInstaller                       |

---

## 🔐 Default Credentials

| Field    | Value  |
|----------|--------|
| Password | `1234` |

> ⚠️ Change the default password immediately after first login via `admin_config.json`.

---

## 📄 License

This project is proprietary software. All rights reserved.
