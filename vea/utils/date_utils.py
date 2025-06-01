"""
Date utility functions.
"""

from datetime import datetime, date, timedelta
from typing import Optional
import re


def parse_date(date_str: Optional[str]) -> date:
    """
    Parse a date string in YYYY-MM-DD format into a date object.
    If date_str is None, returns today's date.
    """
    if date_str:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError as e:
            raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD.") from e
    return datetime.now().date()


def parse_week_input(input_str: str) -> tuple[date, date]:
    """Parse a week input string and return the start and end date of that ISO week."""
    input_str = input_str.strip()

    # Match YYYY-Www or YYYY-ww
    match = re.match(r"^(\d{4})-W?(\d{1,2})$", input_str)
    if match:
        year, week = int(match.group(1)), int(match.group(2))
    elif re.match(r"^\d{1,2}$", input_str):  # Only week number, assume current year
        year = datetime.today().year
        week = int(input_str)
    else:
        # Try to parse as regular date and extract ISO week
        dt = datetime.strptime(input_str, "%Y-%m-%d")
        year, week, _ = dt.isocalendar()

    # ISO weeks start on Monday
    start_of_week = datetime.strptime(f"{year}-W{week:02d}-1", "%G-W%V-%u").date()
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week, end_of_week