#!/usr/bin/env python3
"""
LPU Timetable Scraper & iCalendar Sync
Extracts student timetable from LPU UMS and builds an RFC 5545 compliant timetable.ics file.
Supports both headless (CI/CD) and headed (interactive local desktop) execution.
"""

import os
import sys
import re
import datetime
import subprocess
from bs4 import BeautifulSoup
from icalendar import Calendar, Event, Alarm

# Load environment variables from .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

REG_ID = os.environ.get("LPU_REG_ID")
PASSWORD = os.environ.get("LPU_PASSWORD")

COURSES = {
    "CSE111": "Orientation to Computing",
    "CSE326": "Internet Programming",
    "INT108": "Python Programming",
    "INT335": "Design Thinking",
    "MEC136": "Engineering Drawing with AutoCAD",
    "MTH165": "Mathematics for Engineers",
    "PEA305": "Analytical Skills-I",
    "PES318": "Soft Skills-II",
    "PHY110": "Engineering Physics",
    "CHE110": "Engineering Chemistry",
    "ECE131": "Basic Electrical and Electronics",
    "PEL121": "Communication Skills-I",
    "PEL132": "Communication Skills-II",
}

def parse_slot(slot_str):
    """
    Parses a time slot string like '09:00-10:00 AM' or '01:00-02:00 PM' or '11:00-12:00 PM'.
    Returns (start_hour, start_min, end_hour, end_min) in 24-hour format.
    """
    clean_str = slot_str.strip().replace("  ", " ")
    m = re.match(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*([AP]M)", clean_str, re.IGNORECASE)
    if not m:
        return None
    sh, sm, eh, em, med = m.groups()
    sh, sm, eh, em = int(sh), int(sm), int(eh), int(em)
    med = med.upper()

    if med == "PM":
        # At 11:00-12:00 PM or 11:00-01:00 PM, the start hour 11 is AM
        if sh < 12 and sh != 11:
            sh += 12
        if eh != 12:
            eh += 12
    elif med == "AM":
        if sh == 12:
            sh = 0
        if eh == 12:
            eh = 0

    return sh, sm, eh, em

def get_html(headed=False):
    """
    Automates login to LPU UMS and extracts the student timetable HTML using Playwright.
    If headed=True, opens a visible browser window so user can complete Cloudflare Turnstile.
    """
    if not REG_ID or not PASSWORD:
        print("\n[!] ERROR: LPU_REG_ID or LPU_PASSWORD is missing!")
        print("[!] Please check your .env file or GitHub Secrets.\n")
        sys.exit(1)

    from playwright.sync_api import sync_playwright

    print(f"[*] Starting browser (headed={headed}) for User ID: {REG_ID}...")
    with sync_playwright() as p:
        browser_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
        ]
        if headed:
            browser_args.append("--start-maximized")

        browser = p.chromium.launch(
            headless=not headed,
            args=browser_args
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 850} if not headed else None,
            no_viewport=True if headed else False
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        page = context.new_page()

        try:
            from playwright_stealth import Stealth
            stealth = Stealth()
            stealth.apply_stealth_sync(page)
        except Exception:
            pass

        page.on("dialog", lambda dialog: dialog.accept())

        try:
            print("[*] Navigating to UMS Login page (https://ums.lpu.in/lpuums/LoginNew.aspx)...")
            page.goto("https://ums.lpu.in/lpuums/LoginNew.aspx", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2000)

            # Pre-fill credentials
            user_loc = page.locator('input[name*="txtUserName"], #txtU, input[type="text"]').first
            if user_loc.is_visible():
                print("[*] Entering User ID...")
                user_loc.fill(REG_ID)

            pwd_loc = page.locator('input[name*="txtPassword"], input[type="password"]').first
            if pwd_loc.is_visible():
                print("[*] Entering Password...")
                pwd_loc.fill(PASSWORD)

            if headed:
                print("\n" + "="*65)
                print("[*] BROWSER WINDOW IS OPEN ON YOUR SCREEN!")
                print("[*] If Cloudflare Turnstile ('Verify you are human') appears:")
                print("    👉 Simply click the checkbox in the browser window.")
                print("[*] If credentials are filled, click the orange 'Login' button.")
                print("="*65 + "\n")

                # In headed mode, wait for user or auto-login to leave LoginNew.aspx
                print("[*] Waiting for login to complete (up to 90 seconds)...")
                logged_in = False
                for _ in range(90):
                    page.wait_for_timeout(1000)
                    cur_url = page.url.lower()
                    if "loginnew.aspx" not in cur_url and "lpuums" in cur_url:
                        print(f"[+] Login detected! Redirected to: {page.url}")
                        logged_in = True
                        break
                    # If still on login page and login button is visible, try auto-click if turnstile cleared
                    token = page.locator("[name*='cf-turnstile-response']").first.input_value() if page.locator("[name*='cf-turnstile-response']").count() > 0 else ""
                    if token and len(token) > 20:
                        btn = page.locator('input[name*="btnSubmit"], input[value="Login"]').first
                        if btn.is_visible():
                            print("[*] Turnstile verified! Auto-clicking Login button...")
                            btn.click()
                
                if not logged_in and "loginnew.aspx" in page.url.lower():
                    print("[-] Timed out waiting for login. Continuing attempt to navigate to report...")
            else:
                # Headless automated flow
                for f in page.frames:
                    if "challenges.cloudflare.com" in f.url or "turnstile" in f.url:
                        try:
                            box = f.frame_element().bounding_box()
                            if box:
                                page.mouse.click(box["x"] + 28, box["y"] + box["height"] / 2)
                                page.wait_for_timeout(3000)
                        except Exception:
                            pass
                        break

                submit_loc = page.locator('input[name*="btnSubmit"], input[value="Login"], input[type="submit"]').first
                if submit_loc.is_visible():
                    submit_loc.click()
                    page.wait_for_timeout(3000)

            # Navigate directly to Student Timetable Report
            print("[*] Opening Student Timetable Report (frmStudentTimeTable.aspx)...")
            page.goto("https://ums.lpu.in/lpuums/Reports/frmStudentTimeTable.aspx", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3000)

            print("[*] Waiting for timetable grid table...")
            try:
                page.wait_for_selector('table[class*="139"]', timeout=30000)
                print("[+] Located official timetable table!")
            except Exception as e:
                print(f"[-] Selector notice: {e}")
                page.screenshot(path="debug_error.png")

            content = page.content()
            for frame in page.frames:
                try:
                    f_html = frame.content()
                    if "139" in f_html:
                        content += "\n" + f_html
                except Exception:
                    pass

            # Save local HTML copy as backup
            with open("timetable.html", "w", encoding="utf-8") as f:
                f.write(content)
            print("[+] Saved raw timetable backup to timetable.html")

            browser.close()
            return content

        except Exception as err:
            print(f"[!] Browser error: {err}")
            try:
                page.screenshot(path="debug_error.png")
            except Exception:
                pass
            browser.close()
            raise err

def build_ics(html, output_path="timetable.ics", num_weeks=4):
    """
    Parses the timetable HTML table and writes an RFC 5545 compliant .ics calendar file.
    Generates rolling events for `num_weeks` starting from the target Monday.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_=lambda c: c and "139" in c)
    if not table:
        # Fallback: search for any table containing time slots
        for tbl in soup.find_all("table"):
            if tbl.find(string=re.compile(r"\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}")):
                table = tbl
                break

    if not table:
        print("[!] Error: Could not locate timetable table in HTML.")
        if os.path.exists(output_path):
            print(f"[*] Keeping existing {output_path} file.")
            return True
        return False

    cal = Calendar()
    cal.add("prodid", "-//LPU Sync//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "LPU Timetable")
    cal.add("x-wr-timezone", "Asia/Kolkata")

    today = datetime.date.today()
    if today.weekday() in (5, 6):
        base_monday = today + datetime.timedelta(days=(7 - today.weekday()))
    else:
        base_monday = today - datetime.timedelta(days=today.weekday())

    events_count = 0
    now_utc = datetime.datetime.now(datetime.timezone.utc)

    # Rolling schedule (e.g. 4 weeks coverage)
    target_mondays = [base_monday + datetime.timedelta(weeks=w) for w in range(num_weeks)]

    for tr in table.find_all("tr"):
        tds = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        if len(tds) < 6:
            continue

        times = parse_slot(tds[0])
        if not times:
            continue
        sh, sm, eh, em = times

        # Loop through Monday to Friday (indices 0 to 4 correspond to tds[1] to tds[5])
        # Also include Saturday (tds[6]) if available in row
        max_days = min(len(tds) - 1, 6)

        for day_idx in range(max_days):
            val = tds[day_idx + 1].strip()
            if not val or val == "\xa0" or "Project Work" in val or "Other Weekly Activities" in val:
                continue

            c_m = re.search(r"C:\s*([A-Za-z0-9]+)", val)
            r_m = re.search(r"R:\s*([A-Za-z0-9\-]+)", val)
            s_m = re.search(r"S:\s*([A-Za-z0-9\-]+)", val)
            g_m = re.search(r"G:\s*([A-Za-z0-9\-]+)", val)

            code = c_m.group(1).upper() if c_m else "CLASS"
            room = r_m.group(1) if r_m else "LPU Campus"
            section = s_m.group(1) if s_m else "N/A"
            group = g_m.group(1) if g_m else "N/A"
            title = COURSES.get(code, code)

            type_char = val.split()[0].upper() if val else ""
            type_name = "Class"
            if type_char == "L":
                type_name = "Lecture"
            elif type_char == "P":
                type_name = "Practical / Lab"
            elif type_char == "T":
                type_name = "Tutorial"

            # Generate event for each targeted week
            for target_mon in target_mondays:
                event_date = target_mon + datetime.timedelta(days=day_idx)
                dtstart = datetime.datetime.combine(event_date, datetime.time(sh, sm))
                dtend = datetime.datetime.combine(event_date, datetime.time(eh, em))

                ev = Event()
                ev.add("summary", f"{code}: {title}")
                ev.add("location", f"Room {room}, LPU")
                ev.add("description", f"Course: {title} ({code})\nType: {type_name}\nRoom: {room}\nSection: {section}\nGroup: {group}\nRaw: {val}")
                ev.add("dtstart", dtstart)
                ev.add("dtend", dtend)
                ev.add("dtstamp", now_utc)

                uid = f"lpu-{code}-{event_date.strftime('%Y%m%d')}-{sh:02d}{sm:02d}@lpu-sync"
                ev.add("uid", uid)

                alarm = Alarm()
                alarm.add("action", "DISPLAY")
                alarm.add("description", f"Upcoming class: {code} in Room {room}")
                alarm.add("trigger", datetime.timedelta(minutes=-15))
                ev.add_component(alarm)

                cal.add_component(ev)
                events_count += 1

    with open(output_path, "wb") as f:
        f.write(cal.to_ical())

    print(f"[+] Successfully wrote {events_count} class events to {output_path}")
    return True

def push_to_github():
    """
    Commits timetable.ics and pushes to GitHub Pages branch.
    """
    try:
        print("[*] Pushing updated timetable.ics to GitHub...")
        subprocess.run(["git", "add", "timetable.ics"], check=True)
        # Check if there are staged changes
        res = subprocess.run(["git", "diff", "--staged", "--quiet"])
        if res.returncode != 0:
            subprocess.run(["git", "commit", "-m", "Sync timetable.ics from local run"], check=True)
            subprocess.run(["git", "push", "origin", "main"], check=True)
            print("[+] Successfully pushed updated timetable to GitHub Pages!")
        else:
            print("[*] timetable.ics is already up-to-date on GitHub.")
    except Exception as e:
        print(f"[-] Git push notice: {e}")

if __name__ == "__main__":
    is_headed = "--headed" in sys.argv or os.environ.get("HEADED", "").lower() in ("true", "1")
    do_push = "--push" in sys.argv or os.environ.get("AUTO_PUSH", "").lower() in ("true", "1")

    # If an HTML file path is supplied directly as an argument
    html_file_arg = None
    for arg in sys.argv[1:]:
        if arg.endswith(".html") and os.path.exists(arg):
            html_file_arg = arg
            break

    html_content = None
    if html_file_arg:
        print(f"[*] Reading timetable HTML from local file: {html_file_arg}")
        with open(html_file_arg, "r", encoding="utf-8") as f:
            html_content = f.read()
    elif os.environ.get("HTML_FILE") and os.path.exists(os.environ["HTML_FILE"]):
        print(f"[*] Reading timetable HTML from environment HTML_FILE: {os.environ['HTML_FILE']}")
        with open(os.environ["HTML_FILE"], "r", encoding="utf-8") as f:
            html_content = f.read()
    else:
        html_content = get_html(headed=is_headed)

    if html_content:
        success = build_ics(html_content, "timetable.ics")
        if success and do_push:
            push_to_github()
    else:
        print("[!] Error: No HTML content extracted.")
        sys.exit(1)
