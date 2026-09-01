#!/usr/bin/env python3
"""
Pulls the latest IDP data from Smartsheet and regenerates index.html
for the public IDP Registry dashboard.

Run manually:   SMARTSHEET_TOKEN=xxxx python3 update_dashboard.py
Run in CI:      set the SMARTSHEET_TOKEN secret (see .github/workflows/daily-update.yml)
"""

import os
import sys
import json
import datetime
import requests

SHEET_ID = 1961081999150980  # "IDP Tracking: Master" sheet
TEMPLATE_FILE = "index_template.html"
OUTPUT_FILE = "index.html"


def fetch_sheet(token: str) -> dict:
    url = f"https://api.smartsheet.com/2.0/sheets/{SHEET_ID}"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def clean_num(value):
    """Turn '5.0' -> '5', '1969.0' -> '1969', leave other strings alone."""
    if value is None:
        return "-"
    s = str(value)
    if s.endswith(".0"):
        s = s[:-2]
    return s


def parse_programs(sheet: dict):
    """
    Rows come in two flavors on this sheet:
      - "program" rows carry a Review Status value (parent record)
      - "plan" rows carry a Plan Code value (child degree/major/minor record)
    A plan row belongs to whichever program row precedes it.
    """
    col_title_by_id = {c["id"]: c["title"] for c in sheet["columns"]}

    programs = []
    current = None

    for row in sheet["rows"]:
        cells = {}
        for cell in row.get("cells", []):
            title = col_title_by_id.get(cell["columnId"])
            value = cell.get("displayValue", cell.get("value"))
            if title and value is not None:
                cells[title] = value

        if "Review Status" in cells:
            current = {
                "name": str(cells.get("Department", "")).replace(" (UG)", "").strip(),
                "level": cells.get("GR/UG?", ""),
                "reviewTerm": clean_num(cells.get("Review Term (in years)", "-")),
                "initiated": clean_num(cells.get("Program Initiated", "-")),
                "authPeriod": str(cells.get("Authorization Period", "-")),
                "nextReview": str(cells.get("Next Review Cycle", "-")),
                "senate": str(cells.get("Subject to Faculty Senate Review?", "-")),
                "status": str(cells.get("Review Status", "-")),
                "plans": [],
            }
            programs.append(current)
        elif "Plan Code" in cells or "Program Title" in cells:
            plan = {
                "code": str(cells.get("Plan Code", cells.get("Department", ""))),
                "title": str(cells.get("Program Title", "")),
                "degree": str(cells.get("Degree Designation", "-")),
                "type": str(cells.get("Academic Plan Type", "-")),
                "options": str(cells.get("Academic Options", "-")),
                "idp": str(cells.get("Interdisciplinary Program (IDP)?", "-")),
            }
            if current is not None:
                current["plans"].append(plan)

    return programs


def main():
    token = os.environ.get("SMARTSHEET_TOKEN")
    if not token:
        sys.exit("Set the SMARTSHEET_TOKEN environment variable before running.")

    sheet = fetch_sheet(token)
    programs = parse_programs(sheet)

    if not programs:
        sys.exit("No programs parsed from the sheet — aborting so we don't publish an empty dashboard.")

    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    today = datetime.datetime.now().strftime("%B %-d, %Y")
    html = html.replace("__PROGRAMS_JSON__", json.dumps(programs))
    html = html.replace("__LAST_UPDATED__", today)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Wrote {OUTPUT_FILE} with {len(programs)} programs as of {today}.")


if __name__ == "__main__":
    main()
