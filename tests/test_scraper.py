import os
import tempfile
import unittest
from icalendar import Calendar
from scraper import parse_slot, build_ics

class TestScraper(unittest.TestCase):
    def test_parse_slot(self):
        cases = [
            ("09:00-10:00 AM", (9, 0, 10, 0)),
            ("10:00-11:00 AM", (10, 0, 11, 0)),
            ("11:00-12:00 PM", (11, 0, 12, 0)),
            ("12:00-01:00 PM", (12, 0, 13, 0)),
            ("01:00-02:00 PM", (13, 0, 14, 0)),
            ("02:00-03:00 PM", (14, 0, 15, 0)),
            ("03:00-04:00 PM", (15, 0, 16, 0)),
            ("04:00-05:00 PM", (16, 0, 17, 0)),
            ("11:00-01:00 PM", (11, 0, 13, 0)),
            ("09:00-11:00 AM", (9, 0, 11, 0)),
        ]
        for slot_str, expected in cases:
            with self.subTest(slot_str=slot_str):
                result = parse_slot(slot_str)
                self.assertEqual(result, expected, f"Failed for {slot_str}")

    def test_build_ics_from_html(self):
        sample_html = """
        <html>
        <body>
            <table class="A39c79c0248bd4d3ebd2a62e5964d1a25139">
                <tr>
                    <th>Timing</th>
                    <th>Mon</th>
                    <th>Tue</th>
                    <th>Wed</th>
                    <th>Thu</th>
                    <th>Fri</th>
                    <th>Sat</th>
                </tr>
                <tr>
                    <td>09:00-10:00 AM</td>
                    <td>L / G:1 C:CSE326 / R:38-605 / S:K21AB</td>
                    <td>P / G:1 C:INT108 / R:34-201 / S:K21AB</td>
                    <td>Project Work/ Other Weekly Activities</td>
                    <td>&nbsp;</td>
                    <td>L / G:1 C:MTH165 / R:33-402 / S:K21AB</td>
                    <td>&nbsp;</td>
                </tr>
                <tr>
                    <td>01:00-02:00 PM</td>
                    <td>L / G:1 C:CSE111 / R:38-501 / S:K21AB</td>
                    <td>&nbsp;</td>
                    <td>L / G:1 C:MEC136 / R:36-101 / S:K21AB</td>
                    <td>L / G:1 C:INT335 / R:38-602 / S:K21AB</td>
                    <td>&nbsp;</td>
                    <td>&nbsp;</td>
                </tr>
            </table>
        </body>
        </html>
        """
        with tempfile.NamedTemporaryFile(suffix=".ics", delete=False) as tf:
            out_file = tf.name

        try:
            success = build_ics(sample_html, output_path=out_file, num_weeks=2)
            self.assertTrue(success)

            with open(out_file, "rb") as f:
                cal = Calendar.from_ical(f.read())

            events = [c for c in cal.walk() if c.name == "VEVENT"]
            # 6 active classes across 2 weeks = 12 events
            self.assertEqual(len(events), 12)

            for ev in events:
                self.assertIn("Room", str(ev.get("location")))
                self.assertIsNotNone(ev.get("uid"))
                self.assertIsNotNone(ev.get("dtstamp"))
                self.assertIsNotNone(ev.get("dtstart"))
                self.assertIsNotNone(ev.get("dtend"))

                # Check 15-minute alarm
                alarms = [a for a in ev.walk() if a.name == "VALARM"]
                self.assertEqual(len(alarms), 1)
                self.assertEqual(alarms[0].get("action"), "DISPLAY")
        finally:
            if os.path.exists(out_file):
                os.remove(out_file)

if __name__ == "__main__":
    unittest.main()
