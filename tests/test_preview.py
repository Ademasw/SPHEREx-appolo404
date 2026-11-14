import numpy as np
from app.preview import align_nearest, make_grid


def test_alignment_preserves_sky_position_under_pixel_translation():
    target, size = make_grid(130, -7, fov_deg=0.02)
    source = target.deepcopy()
    source.wcs.crpix += [2, 1]
    image = np.zeros((size + 3, size + 3))
    image[4, 5] = 17
    result = align_nearest(image, source, target, size)
    assert result[3, 3] == 17
    assert np.nansum(result) == 17


def test_invalid_source_pixels_are_not_rendered():
    grid, size = make_grid(130, -7, fov_deg=0.02)
    valid = np.ones((size, size), dtype=bool)
    valid[2, 3] = False
    result = align_nearest(np.ones((size, size)), grid, grid, size, valid)
    assert np.isnan(result[2, 3])
    assert result[3, 2] == 1
