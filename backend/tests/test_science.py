from app.science import matched_range, spectrum, visit_quality


def test_matched_range_and_quality():
    first = {"wavelength_min_um": 1.0, "wavelength_max_um": 2.0,
             "usable_grid_fraction": .9, "n_frames": 10}
    second = {"wavelength_min_um": 1.5, "wavelength_max_um": 2.5,
              "usable_grid_fraction": .6, "n_frames": 4}
    assert matched_range(first, second) == {"min_um": 1.5, "max_um": 2.0}
    assert visit_quality(first)["level"] == "good"
    assert visit_quality(second)["level"] == "partial"


def test_spectrum_omits_saturated_frames():
    manifests = [{"query": {"detector": "D1"}, "frames": [
        {"wavelength_um": 1.0, "time_utc": "2026-01-01", "photometry": {"flux": 4, "error": 1},
         "saturated_at_target": False},
        {"wavelength_um": 1.1, "time_utc": "2026-01-01", "photometry": {"flux": 5, "error": 1},
         "saturated_at_target": True},
    ]}]
    points = spectrum(manifests)
    assert len(points) == 1
    assert points[0]["flux"] == 4
