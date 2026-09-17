#!/bin/bash
cd "$(dirname "$0")"

echo "=========================================================="
echo "          📅 LPU Timetable 1-Click Sync for Mac          "
echo "=========================================================="
echo ""

# Ensure virtual environment exists
if [ ! -d ".venv" ]; then
    echo "[*] Initializing Python environment..."
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    .venv/bin/playwright install chromium
fi

echo "[*] Launching browser to fetch timetable..."
echo "[*] A Chrome window will open. If Cloudflare asks to verify,"
echo "    just check the box on screen."
echo ""

.venv/bin/python scraper.py --headed --push

echo ""
echo "=========================================================="
echo "  ✅ Done! Your timetable has been synced and pushed.     "
echo "  Your iPhone / Mac Calendar will update automatically.  "
echo "=========================================================="
echo ""
read -p "Press [Enter] to close..."
