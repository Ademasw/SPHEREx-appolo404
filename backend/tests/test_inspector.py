import numpy as np
import pytest
from app.inspector import aperture_spectrum, coverage, inspect_pixel
from app.preview import make_grid
from app.inspector import spectral_band


def fixture(tmp_path):
    grid, size = make_grid(10, -20, .05)
    yy, xx = np.indices((size, size))
    image = np.ones((size, size)) * 5
    image[(xx-14)**2 + (yy-14)**2 <= 4] += 10
    (tmp_path / 'frames').mkdir()
    np.savez(tmp_path/'frames/0.npz', data=image, variance=np.ones_like(image),
             saturated=np.zeros_like(image, dtype=bool), wavelength_um=np.full_like(image, 2.),
             bandwidth_um=np.full_like(image, .1), flags=np.full_like(image, 1 << 21, dtype=np.int64),
             flags_covered=np.ones_like(image, dtype=bool))
    return {'query': {'detector':'D3'}, 'grid':{'header':dict(grid.to_header()),'size_px':size},
            'processing':{'unit':'MJy/sr'},'frames':[{'index':0,'visit':0,'obs_id':'real-input-id',
            'time_utc':'2025-01-01T00:00:00','image_url':'/0.png','flag_definitions':{'MSKN0021':'SOURCE'}}]}


def test_aperture_spectrum_uses_numerical_units_background_and_single_epoch(tmp_path):
    manifest=fixture(tmp_path)
    result=aperture_spectrum(tmp_path,manifest,14,14,0)
    assert result['unit']=='Jy'
    point=result['points'][0]
    expected=13 * 10 * (6.2/3600 * np.pi/180)**2 * 1e6
    assert point['flux']==pytest.approx(expected,rel=1e-6)
    assert point['wavelength_um']==2
    assert point['usable_aperture_fraction']==1
    assert aperture_spectrum(tmp_path,manifest,14,14,1)['points']==[]
    with pytest.raises(ValueError):
        aperture_spectrum(tmp_path,manifest,float('nan'),14,0)


def test_inspection_preserves_source_flag_and_wcs(tmp_path):
    manifest=fixture(tmp_path)
    pixel=inspect_pixel(tmp_path,manifest,0,14,14)
    assert pixel['flags']==['SOURCE'] and pixel['value']==15
    assert pixel['wavelength_um']==2 and pixel['covered']
    assert coverage(tmp_path,manifest)['frames'][0]['usable_fraction']==1
    with pytest.raises(ValueError,match='outside'):
        inspect_pixel(tmp_path,manifest,0,-1,0)


def test_spectral_range_uses_pixel_wavelengths_and_keeps_missing_channels_empty(tmp_path):
    manifest=fixture(tmp_path)
    manifest['visits']=[{}]
    image, variance, count=spectral_band(tmp_path,manifest,0,1.9,2.1)
    assert image[14,14]==15 and count[14,14]==1 and variance[14,14]==1
    image, variance, count=spectral_band(tmp_path,manifest,0,3.,4.)
    assert np.isnan(image).all() and np.isnan(variance).all() and not count.any()
