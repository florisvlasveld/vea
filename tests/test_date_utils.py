from datetime import datetime, timedelta

from vea.utils.date_utils import parse_week_input


def test_parse_week_input_year_with_w():
    start, end = parse_week_input("2025-W22")
    expected_start = datetime.strptime("2025-W22-1", "%G-W%V-%u").date()
    assert start == expected_start
    assert end == expected_start + timedelta(days=6)


def test_parse_week_input_year_without_w():
    start, end = parse_week_input("2025-22")
    expected_start = datetime.strptime("2025-W22-1", "%G-W%V-%u").date()
    assert start == expected_start
    assert end == expected_start + timedelta(days=6)


def test_parse_week_input_week_only():
    year = datetime.today().year
    start, end = parse_week_input("22")
    expected_start = datetime.strptime(f"{year}-W22-1", "%G-W%V-%u").date()
    assert start == expected_start
    assert end == expected_start + timedelta(days=6)


def test_parse_week_input_from_date():
    start, end = parse_week_input("2025-05-28")
    expected_start = datetime.strptime("2025-W22-1", "%G-W%V-%u").date()
    assert start == expected_start
    assert end == expected_start + timedelta(days=6)
