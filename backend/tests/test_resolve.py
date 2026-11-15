import pytest

from app.resolve import ResolveError, parse_coordinates


def test_decimal_degrees():
    assert parse_coordinates("133.7951 -7.2451") == (133.7951, -7.2451)
    assert parse_coordinates("133.7951, -7.2451") == (133.7951, -7.2451)


def test_sexagesimal_hours():
    ra, dec = parse_coordinates("08h55m10.831s -07d14m42.53s")
    assert ra == pytest.approx(133.79513, abs=1e-4)
    assert dec == pytest.approx(-7.24515, abs=1e-4)
    ra, dec = parse_coordinates("08:55:10.831 -07:14:42.53")
    assert ra == pytest.approx(133.79513, abs=1e-4)


def test_names_are_not_coordinates():
    assert parse_coordinates("Barnard's Star") is None
    assert parse_coordinates("WISE 0855") is None
    assert parse_coordinates("R Dra") is None


def test_out_of_range_rejected():
    with pytest.raises(ResolveError):
        parse_coordinates("400 10")
