#!/usr/bin/env python3
"""
LPU Timetable Scraper & iCalendar Sync
Extracts student timetable from LPU UMS and builds an RFC 5545 compliant timetable.ics file.
Includes:
- 10-minute advance notification reminders for each class.
- Daily 8:00 AM Morning Briefing notification summarizing all classes for that day.
- Full RFC 5545 VTIMEZONE Asia/Kolkata support for Apple Calendar / iOS.
"""

import os
import sys
import re
import datetime
import zoneinfo
import subprocess
from bs4 import BeautifulSoup
from icalendar import Calendar, Event, Alarm, Timezone, TimezoneStandard

TZ_KOLKATA = zoneinfo.ZoneInfo("Asia/Kolkata")

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
    Parses a time slot string like '09:20-10:10 AM' or '01:30-02:20 PM' or '11:50-12:40 AM'.
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
        # Handle UMS bug like 11:50-12:40 AM where 12:40 is actually 12:40 PM noon
        if sh == 11 and eh == 12:
            eh = 12
        elif sh == 12:
            sh = 0
        elif eh == 12:
            eh = 12

    return sh, sm, eh, em

def extract_course_titles(soup):
    """
    Automatically extracts course code to course title mapping from table in UMS HTML.
    """
    course_map = {}
    for tr in soup.find_all("tr"):
        tds = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        for idx, text in enumerate(tds):
            if re.match(r"^[A-Z]{2,4}\d{3}[A-Z]?$", text.strip()):
                code = text.strip()
                if len(tds) > idx + 2:
                    title = tds[idx + 2].title()
                    course_map[code] = title
    return course_map

def build_ics(html, output_path="timetable.ics", num_weeks=4):
    """
    Parses the timetable HTML table and writes an RFC 5545 compliant .ics calendar file.
    Includes:
    - 10-minute advance notification reminders for each class.
    - Daily 8:00 AM Morning Briefing notification summarizing all classes for that day.
    - Full Asia/Kolkata VTIMEZONE definition for Apple Calendar / iOS.
    """
    soup = BeautifulSoup(html, "html.parser")
    
    course_titles = extract_course_titles(soup)
    merged_courses = {**COURSES, **course_titles}

    table = soup.find("table", class_=lambda c: c and any("139" in x for x in (c if isinstance(c, list) else [c])))
    if not table:
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

    # Add standard VTIMEZONE for Asia/Kolkata
    vtz = Timezone()
    vtz.add("tzid", "Asia/Kolkata")
    vtz_std = TimezoneStandard()
    vtz_std.add("dtstart", datetime.datetime(1970, 1, 1, 0, 0, 0))
    vtz_std.add("tzoffsetfrom", datetime.timedelta(hours=5, minutes=30))
    vtz_std.add("tzoffsetto", datetime.timedelta(hours=5, minutes=30))
    vtz_std.add("tzname", "IST")
    vtz.add_component(vtz_std)
    cal.add_component(vtz)

    today = datetime.datetime.now(TZ_KOLKATA).date()
    if today.weekday() in (5, 6):
        base_monday = today + datetime.timedelta(days=(7 - today.weekday()))
    else:
        base_monday = today - datetime.timedelta(days=today.weekday())

    events_count = 0
    briefings_count = 0
    now_utc = datetime.datetime.now(datetime.timezone.utc)

    # Rolling schedule (4 weeks coverage)
    target_mondays = [base_monday + datetime.timedelta(weeks=w) for w in range(num_weeks)]

    day_classes = {i: [] for i in range(6)}

    for tr in table.find_all("tr"):
        tds = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        if len(tds) < 6:
            continue

        timing_col = None
        times = None
        for idx, text in enumerate(tds):
            parsed = parse_slot(text)
            if parsed:
                timing_col = idx
                times = parsed
                break

        if timing_col is None or not times:
            continue
        sh, sm, eh, em = times

        max_days = min(len(tds) - 1 - timing_col, 6)

        for day_idx in range(max_days):
            val = tds[timing_col + 1 + day_idx].strip()
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
            title = merged_courses.get(code, code)

            type_char = val.split()[0].upper() if val else ""
            type_name = "Class"
            if type_char == "L":
                type_name = "Lecture"
            elif type_char == "P":
                type_name = "Practical / Lab"
            elif type_char == "T":
                type_name = "Tutorial"

            class_info = {
                "code": code,
                "title": title,
                "room": room,
                "section": section,
                "group": group,
                "type_name": type_name,
                "sh": sh,
                "sm": sm,
                "eh": eh,
                "em": em,
                "raw": val
            }
            day_classes[day_idx].append(class_info)

    for day_idx in day_classes:
        day_classes[day_idx].sort(key=lambda x: (x["sh"], x["sm"]))

    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

    # 1. Add individual Class Events (with 10-min reminder & proper TZID)
    for day_idx, classes in day_classes.items():
        for c in classes:
            for target_mon in target_mondays:
                event_date = target_mon + datetime.timedelta(days=day_idx)
                dtstart = datetime.datetime.combine(event_date, datetime.time(c["sh"], c["sm"]), tzinfo=TZ_KOLKATA)
                dtend = datetime.datetime.combine(event_date, datetime.time(c["eh"], c["em"]), tzinfo=TZ_KOLKATA)

                ev = Event()
                ev.add("summary", f"{c['code']}: {c['title']}")
                ev.add("location", f"Room {c['room']}, LPU")
                ev.add("description", f"Course: {c['title']} ({c['code']})\nType: {c['type_name']}\nRoom: {c['room']}\nSection: {c['section']}\nGroup: {c['group']}")
                ev.add("dtstart", dtstart)
                ev.add("dtend", dtend)
                ev.add("dtstamp", now_utc)

                uid = f"lpu-{c['code']}-{event_date.strftime('%Y%m%d')}-{c['sh']:02d}{c['sm']:02d}@lpu-sync"
                ev.add("uid", uid)

                # 10-Minute Reminder Alert
                alarm = Alarm()
                alarm.add("action", "DISPLAY")
                alarm.add("description", f"⏰ Class in 10 mins: {c['code']} in Room {c['room']}")
                alarm.add("trigger", datetime.timedelta(minutes=-10))
                ev.add_component(alarm)

                cal.add_component(ev)
                events_count += 1

    # 2. Add Daily Morning Schedule Briefing (8:00 AM notification)
    for day_idx, classes in day_classes.items():
        if not classes:
            continue
        day_name = day_names[day_idx]
        first_c = classes[0]

        summary_lines = [f"☀️ Good morning! Here is your class schedule for {day_name}:\n"]
        for idx, c in enumerate(classes, 1):
            time_str = f"{c['sh']:02d}:{c['sm']:02d} - {c['eh']:02d}:{c['em']:02d}"
            summary_lines.append(f"{idx}. {time_str} | {c['code']} in Room {c['room']} ({c['type_name']}) - {c['title']}")

        summary_body = "\n".join(summary_lines)

        for target_mon in target_mondays:
            event_date = target_mon + datetime.timedelta(days=day_idx)
            brief_start = datetime.datetime.combine(event_date, datetime.time(8, 0), tzinfo=TZ_KOLKATA)
            brief_end = datetime.datetime.combine(event_date, datetime.time(8, 30), tzinfo=TZ_KOLKATA)

            ev_brief = Event()
            ev_brief.add("summary", f"📋 Today: {len(classes)} Classes (First @ {first_c['sh']:02d}:{first_c['sm']:02d} in {first_c['room']})")
            ev_brief.add("location", "Lovely Professional University")
            ev_brief.add("description", summary_body)
            ev_brief.add("dtstart", brief_start)
            ev_brief.add("dtend", brief_end)
            ev_brief.add("dtstamp", now_utc)

            uid_brief = f"lpu-briefing-{event_date.strftime('%Y%m%d')}@lpu-sync"
            ev_brief.add("uid", uid_brief)

            # 8:00 AM Alarm Notification
            alarm_brief = Alarm()
            alarm_brief.add("action", "DISPLAY")
            alarm_brief.add("description", f"📋 Today's Schedule: {len(classes)} classes. First class: {first_c['code']} at {first_c['sh']:02d}:{first_c['sm']:02d} AM in Room {first_c['room']}.")
            alarm_brief.add("trigger", datetime.timedelta(minutes=0))
            ev_brief.add_component(alarm_brief)

            cal.add_component(ev_brief)
            briefings_count += 1

    # Add a live test alert for verification (5 minutes from now)
    now_kolkata = datetime.datetime.now(TZ_KOLKATA)
    t_start = now_kolkata + datetime.timedelta(minutes=5)
    t_end = t_start + datetime.timedelta(minutes=30)
    ev_test = Event()
    ev_test.add("summary", "🔔 Alert Test: INT108 in Room 34-702A")
    ev_test.add("location", "Room 34-702A, LPU")
    ev_test.add("description", "Testing class notifications on your iPhone.")
    ev_test.add("dtstart", t_start)
    ev_test.add("dtend", t_end)
    ev_test.add("dtstamp", now_utc)
    ev_test.add("uid", f"lpu-live-test-{now_kolkata.strftime('%Y%m%d%H%M%S')}@lpu-sync")

    alarm_test = Alarm()
    alarm_test.add("action", "DISPLAY")
    alarm_test.add("description", "🔔 Class in 10 mins: INT108 in Room 34-702A")
    alarm_test.add("trigger", datetime.timedelta(minutes=-4)) # Alert in ~1-2 minutes
    ev_test.add_component(alarm_test)
    cal.add_component(ev_test)

    with open(output_path, "wb") as f:
        f.write(cal.to_ical())

    print(f"[+] Successfully wrote {events_count} class events (with 10-min alerts), {briefings_count} daily morning summary briefings, and 1 live test alert to {output_path}")
    return True

def push_to_github():
    """
    Commits timetable.ics and pushes to GitHub Pages branch.
    """
    try:
        print("[*] Pushing updated timetable.ics to GitHub...")
        subprocess.run(["git", "add", "timetable.ics"], check=True)
        res = subprocess.run(["git", "diff", "--staged", "--quiet"])
        if res.returncode != 0:
            subprocess.run(["git", "commit", "-m", "Sync timetable.ics with RFC 5545 VTIMEZONE Asia/Kolkata"], check=True)
            subprocess.run(["git", "push", "origin", "main"], check=True)
            print("[+] Successfully pushed updated timetable to GitHub Pages!")
        else:
            print("[*] timetable.ics is already up-to-date on GitHub.")
    except Exception as e:
        print(f"[-] Git push notice: {e}")

if __name__ == "__main__":
    is_headed = "--headed" in sys.argv or os.environ.get("HEADED", "").lower() in ("true", "1")
    do_push = "--push" in sys.argv or os.environ.get("AUTO_PUSH", "").lower() in ("true", "1")

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
        print("[!] No HTML file supplied. Usage: python scraper.py timetable.html --push")
        sys.exit(1)

    if html_content:
        success = build_ics(html_content, "timetable.ics")
        if success and do_push:
            push_to_github()
    else:
        print("[!] Error: No HTML content extracted.")
        sys.exit(1)
