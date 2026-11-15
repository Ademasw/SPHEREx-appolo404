import pytest
from app.astrometry import propagate


def test_stationary_target_stays_fixed():
    result = propagate(130, -7, 0, 0, 2000, 2026)
    assert result["ra_deg"] == pytest.approx(130)
    assert result["dec_deg"] == pytest.approx(-7)


def test_ra_motion_includes_cosine_declination():
    result = propagate(130, 60, 1000, 0, 2000, 2001)
    assert (result["ra_deg"] - 130) * 3600 == pytest.approx(2, abs=0.001)
