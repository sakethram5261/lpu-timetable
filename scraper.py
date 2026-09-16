#!/usr/bin/env python3
"""
LPU Timetable Scraper & iCalendar Sync
Extracts student timetable from LPU UMS and builds an RFC 5545 compliant timetable.ics file.
"""

import os
import sys
import re
import datetime
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

def get_html():
    """
    Automates login to LPU UMS and extracts the student timetable HTML using Playwright.
    """
    if not REG_ID or not PASSWORD:
        raise ValueError("LPU_REG_ID and LPU_PASSWORD environment variables must be set.")

    from playwright.sync_api import sync_playwright

    print(f"[*] Launching Playwright browser for user: {REG_ID}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        # Avoid webdriver automation flags
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        page = context.new_page()

        # Try to apply stealth if library is installed
        try:
            from playwright_stealth import Stealth
            stealth = Stealth()
            stealth.apply_stealth_sync(page)
        except Exception:
            pass

        # Dismiss any popup dialogs automatically
        page.on("dialog", lambda dialog: dialog.accept())

        print("[*] Navigating to UMS Login...")
        page.goto("https://ums.lpu.in/lpuums/LoginNew.aspx", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)

        # Flexible selector matching for username
        user_loc = page.locator('input[name*="txtUserName"], #txtU, input[type="text"]').first
        user_loc.fill(REG_ID)

        # Flexible selector matching for password
        pwd_loc = page.locator('input[name*="txtPassword"], input[type="password"]').first
        pwd_loc.fill(PASSWORD)

        # Check for Cloudflare Turnstile challenge if present
        for f in page.frames:
            if "challenges.cloudflare.com" in f.url or "turnstile" in f.url:
                print("[*] Detected Cloudflare Turnstile, attempting solve...")
                try:
                    frame_el = f.frame_element()
                    box = frame_el.bounding_box()
                    if box:
                        page.mouse.click(box["x"] + 28, box["y"] + box["height"] / 2)
                        page.wait_for_timeout(3000)
                except Exception as e:
                    print(f"[-] Turnstile interaction note: {e}")
                break

        print("[*] Clicking Login button...")
        submit_loc = page.locator('input[name*="btnSubmit"], input[value="Login"], input[type="submit"]').first
        submit_loc.click()

        # Wait for post-login navigation or dashboard
        try:
            page.wait_for_load_state("domcontentloaded", timeout=45000)
        except Exception:
            pass
        page.wait_for_timeout(2000)

        print("[*] Navigating to Student Timetable Report...")
        page.goto("https://ums.lpu.in/lpuums/Reports/frmStudentTimeTable.aspx", wait_until="domcontentloaded", timeout=60000)

        # Wait for the timetable grid table matching class containing '139'
        print("[*] Waiting for timetable grid table...")
        try:
            page.wait_for_selector('table[class*="139"]', timeout=45000)
        except Exception:
            print("[-] Selector table[class*='139'] not found directly, checking fallback...")

        content = page.content()

        # Check all child frames if present (e.g. ReportViewer iframe)
        for frame in page.frames:
            try:
                frame_html = frame.content()
                if "139" in frame_html:
                    content += "\n" + frame_html
            except Exception:
                pass

        browser.close()
        print("[+] Timetable HTML extracted successfully.")
        return content

def build_ics(html, output_path="timetable.ics", num_weeks=2):
    """
    Parses the timetable HTML table and writes an RFC 5545 compliant .ics calendar file.
    Generates rolling events for `num_weeks` starting from the target Monday.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_=lambda c: c and "139" in c)
    if not table:
        # Fallback: search for any table containing slot-like text
        for tbl in soup.find_all("table"):
            if tbl.find(string=re.compile(r"\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}")):
                table = tbl
                break

    if not table:
        print("[!] Error: Could not locate timetable table in HTML.")
        return False

    cal = Calendar()
    cal.add("prodid", "-//LPU Sync//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "LPU Timetable")
    cal.add("x-wr-timezone", "Asia/Kolkata")

    today = datetime.date.today()
    # If today is Saturday (5) or Sunday (6), set target Monday to upcoming Monday
    if today.weekday() in (5, 6):
        base_monday = today + datetime.timedelta(days=(7 - today.weekday()))
    else:
        base_monday = today - datetime.timedelta(days=today.weekday())

    events_count = 0
    now_utc = datetime.datetime.now(datetime.timezone.utc)

    # Rolling schedule (current week and next week)
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

            # Determine Class Type (Lecture, Practical, Tutorial)
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

                # Deterministic UID for Apple/Google Calendar cleanly deduplicating updates
                uid = f"lpu-{code}-{event_date.strftime('%Y%m%d')}-{sh:02d}{sm:02d}@lpu-sync"
                ev.add("uid", uid)

                # 15-minute reminder alert
                alarm = Alarm()
                alarm.add("action", "DISPLAY")
                alarm.add("description", f"Upcoming class: {code} in Room {room}")
                alarm.add("trigger", datetime.timedelta(minutes=-15))
                ev.add_component(alarm)

                cal.add_component(ev)
                events_count += 1

    with open(output_path, "wb") as f:
        f.write(cal.to_ical())

    print(f"[+] Successfully wrote {events_count} events to {output_path}")
    return True

if __name__ == "__main__":
    html_content = None

    # Check if a local HTML file was supplied for testing
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        print(f"[*] Reading HTML from local file: {sys.argv[1]}")
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            html_content = f.read()
    elif os.environ.get("HTML_FILE") and os.path.exists(os.environ["HTML_FILE"]):
        print(f"[*] Reading HTML from environment HTML_FILE: {os.environ['HTML_FILE']}")
        with open(os.environ["HTML_FILE"], "r", encoding="utf-8") as f:
            html_content = f.read()
    else:
        html_content = get_html()

    if html_content:
        build_ics(html_content)
    else:
        print("[!] No HTML content available.")
        sys.exit(1)
