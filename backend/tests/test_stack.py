import numpy as np

from app.preview import make_grid
from app.stack import align_bilinear, combine, group_epochs, measure_source, subtract_background


def test_measure_source_finds_subpixel_centroid():
    rng = np.random.default_rng(1)
    yy, xx = np.indices((31, 31))
    image = 100 * np.exp(-((xx - 15.4) ** 2 + (yy - 14.7) ** 2) / 2.0) + rng.normal(0, 1, (31, 31))
    result = measure_source(image, 15, 15)
    assert abs(result["x"] - 15.4) < 0.1
    assert abs(result["y"] - 14.7) < 0.1
    assert result["peak_snr"] > 30


def test_group_epochs_splits_on_long_gaps():
    times = [60800.0, 60801.5, 60803.0, 61020.0, 61021.0, 61171.0]
    assert group_epochs(times) == [[0, 1, 2], [3, 4], [5]]


def test_group_epochs_handles_unsorted_and_empty():
    assert group_epochs([61020.0, 60800.0, 60801.0]) == [[1, 2], [0]]
    assert group_epochs([]) == []


def test_bilinear_alignment_keeps_subpixel_shift():
    target, size = make_grid(130, -7, fov_deg=0.02)
    source = target.deepcopy()
    source.wcs.crpix += [0.5, 0]  # source grid shifted by half a pixel in x
    image = np.tile(np.arange(size + 4, dtype=float), (size + 4, 1))  # value = x index
    result = align_bilinear(image, source, target, size)
    # target pixel x maps to source pixel x + 0.5, so values increase by 0.5
    assert np.allclose(result[3, 3:8], np.arange(3, 8) + 0.5)


def test_bilinear_alignment_ignores_invalid_pixels():
    grid, size = make_grid(130, -7, fov_deg=0.02)
    valid = np.ones((size, size), dtype=bool)
    valid[2, 3] = False
    result = align_bilinear(np.ones((size, size)), grid, grid, size, valid)
    assert np.isnan(result[2, 3])
    assert result[3, 3] == 1


def test_combine_rejects_single_frame_outlier():
    cube = np.ones((7, 4, 4))
    cube[2, 1, 1] = 1000.0  # cosmic ray in one frame
    stacked, used = combine(cube)
    assert np.allclose(stacked, 1.0)
    assert used[1, 1] == 6
    assert used[0, 0] == 7


def test_combine_weights_by_inverse_variance():
    cube = np.stack([np.full((2, 2), 1.0), np.full((2, 2), 4.0)])
    variance = np.stack([np.full((2, 2), 1.0), np.full((2, 2), 3.0)])
    stacked, _ = combine(cube, variance)
    assert np.allclose(stacked, (1.0 * 1 + 4.0 / 3) / (1 + 1 / 3))


def test_subtract_background_removes_constant_level():
    rng = np.random.default_rng(0)
    frame = 50.0 + rng.normal(0, 1, (40, 40))
    assert abs(np.nanmedian(subtract_background(frame))) < 0.2


def test_background_modes_produce_different_keys():
    from app.pipeline import sequence_key
    assert sequence_key(10, 0, 0.1) == "10.0000_+0.0000_0.1"
    assert sequence_key(10, 0, 0.1, "median") == "10.0000_+0.0000_0.1_med"
    assert sequence_key(10, 0, 0.1, "none") == "10.0000_+0.0000_0.1_raw"
