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


def test_pixelwise_matching_excludes_saturation_and_incompatible_bandpasses(tmp_path):
    import numpy as np
    from astropy.io import fits
    from app.science import matched_difference
    (tmp_path / 'frames').mkdir()
    manifest = {'visits': [{}, {}], 'frames': []}
    for index, (visit, level, wave) in enumerate([(0, 3., 1.), (1, 7., 1.01), (1, 1000., 2.)]):
        saturated = np.zeros((3, 3), dtype=bool)
        saturated[0, 0] = True
        np.savez(tmp_path / 'frames' / f'{index}.npz', data=np.full((3, 3), level),
                 variance=np.ones((3, 3)), saturated=saturated,
                 wavelength_um=np.full((3, 3), wave), bandwidth_um=np.full((3, 3), .1))
        manifest['frames'].append({'index': index, 'visit': visit})
    output = tmp_path / 'difference.png'
    result = matched_difference(tmp_path, manifest, 0, 1, output)
    assert result['usable_grid_fraction'] == 8 / 9
    with fits.open(output.with_suffix('.fits')) as hdus:
        assert np.isnan(hdus[0].data[0, 0])
        assert hdus[0].data[1, 1] == 4  # later minus earlier; incompatible 1000 omitted
        assert hdus['COUNT_B'].data[1, 1] == 1
        assert hdus['VARIANCE'].data[1, 1] == 2
