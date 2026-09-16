# 📅 LPU Timetable Auto-Sync

[![Sync Timetable](https://github.com/sakethram5261/lpu-timetable/actions/workflows/sync.yml/badge.svg)](https://github.com/sakethram5261/lpu-timetable/actions/workflows/sync.yml)

Automate weekly extraction of your Lovely Professional University (LPU) student timetable directly from UMS, generate an RFC 5545 compliant `.ics` calendar feed, and host it via GitHub Pages.

Subscribe **once** on your iPhone or Google Calendar, and your schedule stays automatically updated with exact classroom locations, course codes, and 15-minute start reminders.

---

## 🚀 Live Subscription & Dashboard

The timetable feed and landing dashboard are hosted via GitHub Pages:
- **Dashboard**: `https://sakethram5261.github.io/lpu-timetable/`
- **Calendar Feed (.ics)**: `https://sakethram5261.github.io/lpu-timetable/timetable.ics`
- **1-Tap iPhone Subscription**: `webcal://sakethram5261.github.io/lpu-timetable/timetable.ics`

---

## ✨ Features

- **Automated Sunday Runs**: GitHub Actions runs Playwright headless weekly (Sunday 18:35 UTC / Monday 00:05 IST) to log into UMS and grab fresh timetable changes.
- **Smart 15-Minute Alarms**: Built-in Apple/Google compliant `VALARM` triggers notification 15 minutes before every class.
- **Rich Class Info**: Events include Course code, Course title, Room number (e.g. `38-605`), Section, and Class type (Lecture / Practical / Tutorial).
- **Rolling Schedule**: Keeps rolling 2-week classes with deterministic `UID`s so Apple Calendar and Google Calendar update cleanly without duplicates.

---

## 🛠️ Setup Guide

### 1. Configure GitHub Repository Secrets
To allow GitHub Actions to log into UMS securely:
1. Go to your repository on GitHub: [sakethram5261/lpu-timetable](https://github.com/sakethram5261/lpu-timetable).
2. Navigate to **Settings** > **Secrets and variables** > **Actions**.
3. Under **Repository secrets**, click **New repository secret** and add:
   - `LPU_REG_ID`: Your LPU Registration ID (e.g., `12607258`)
   - `LPU_PASSWORD`: Your LPU UMS Password

### 2. Enable GitHub Pages
1. In your repository, go to **Settings** > **Pages**.
2. Under **Build and deployment** > **Branch**:
   - Select branch: `main`
   - Select folder: `/ (root)`
   - Click **Save**.
3. Your calendar will now be publicly accessible at:
   `https://sakethram5261.github.io/lpu-timetable/timetable.ics`

### 3. Trigger Initial Sync
1. In your repository, click the **Actions** tab.
2. Select **Sync Timetable** from the left sidebar.
3. Click **Run workflow** > **Run workflow** (from branch `main`).
4. Wait ~1 minute for the workflow to complete. It will generate and commit `timetable.ics` to your repository.

---

## 📱 How to Subscribe on iPhone / Apple Calendar

### Method A (Recommended: 1-Tap Safari)
1. On your iPhone, open Safari and go to:
   `https://sakethram5261.github.io/lpu-timetable/`
2. Tap the orange **"Subscribe on iPhone / Mac"** button.
3. In the pop-up prompt, tap **Subscribe**.
4. Set **Auto-Refresh** to **Every Day** or **Every Hour**, then tap **Add**.

### Method B (Manual iOS Settings)
1. On your iPhone, open **Settings** > **Calendar** > **Accounts**.
2. Tap **Add Account** > **Other** > **Add Subscribed Calendar**.
3. Paste the feed URL:
   ```text
   https://sakethram5261.github.io/lpu-timetable/timetable.ics
   ```
4. Tap **Next**, verify details, and tap **Save**.

---

## 🌐 How to Subscribe on Google Calendar

1. Open [Google Calendar](https://calendar.google.com/) in your browser.
2. In the left sidebar, find **Other calendars**, click the **`+`** icon > **From URL**.
3. Paste your subscription URL:
   ```text
   https://sakethram5261.github.io/lpu-timetable/timetable.ics
   ```
4. Click **Add calendar**. Google Calendar will periodically fetch updates automatically.

---

## 💻 Local Development & Testing

1. Clone the repository:
   ```bash
   git clone https://github.com/sakethram5261/lpu-timetable.git
   cd lpu-timetable
   ```
2. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   playwright install chromium
   ```
3. Copy `.env.example` to `.env` and set your credentials:
   ```bash
   cp .env.example .env
   # Edit .env with your registration id and password
   ```
4. Run tests:
   ```bash
   python -m unittest tests/test_scraper.py
   ```
5. Run the scraper manually:
   ```bash
   python scraper.py
   ```

---

## 🔒 Security Note
- Your credentials (`LPU_REG_ID` and `LPU_PASSWORD`) are stored exclusively in GitHub Secrets or your local `.env`.
- `.env` is listed in `.gitignore` and is never committed to GitHub.
