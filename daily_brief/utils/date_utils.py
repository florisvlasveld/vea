"""
Date utility functions.
"""

from datetime import datetime, date
from typing import Optional


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
