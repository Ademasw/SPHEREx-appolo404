"""Read numerical sequence products. No measurements are inferred from PNGs."""
import math
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy import units as u
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_area


def spectral_band(folder, manifest, visit, low, high):
    """Stack only usable measurements whose local band centers fall in [low, high]."""
    if not all(math.isfinite(v) for v in (low, high)) or not (.7 <= low < high <= 5.1):
        raise ValueError('Choose a wavelength interval inside 0.7–5.1 microns')
    if visit < 0 or visit >= len(manifest.get('visits', [])):
        raise ValueError('Choose an available visit')
    size = manifest['grid']['size_px']
    weighted, weights = np.zeros((size, size)), np.zeros((size, size))
    count = np.zeros((size, size), dtype=np.int32)
    for frame in manifest.get('frames', []):
        if frame.get('visit') != visit:
            continue
        with np.load(folder / 'frames' / f"{frame['index']}.npz") as data:
            if 'wavelength_um' not in data.files:
                continue
            good = (np.isfinite(data['data']) & np.isfinite(data['variance']) & (data['variance'] > 0)
                    & ~data['saturated'] & (data['wavelength_um'] >= low) & (data['wavelength_um'] <= high))
            w = np.divide(1., data['variance'], out=np.zeros_like(weights), where=good)
            weighted += np.where(good, data['data'], 0) * w
            weights += w
            count += good
    stack = np.divide(weighted, weights, out=np.full_like(weights, np.nan), where=weights > 0)
    variance = np.divide(1., weights, out=np.full_like(weights, np.nan), where=weights > 0)
    return stack, variance, count


def band_fits(stack, variance, count, manifest, visit, low, high):
    import io
    header = fits.Header(manifest['grid']['header'])
    header['BUNIT'], header['WAVEMIN'], header['WAVEMAX'], header['VISIT'] = 'MJy/sr', low, high, visit
    header['HISTORY'] = 'Local central wavelength selection; inverse variance mean; diagnostic. No PSF matching.'
    header['HISTORY'] = 'Collections: ' + ', '.join(manifest.get('archive', {}).get('collections', []))
    output = io.BytesIO()
    fits.HDUList([fits.PrimaryHDU(stack.astype(np.float32), header),
                  fits.ImageHDU(variance.astype(np.float32), name='VARIANCE'),
                  fits.ImageHDU(count, name='COUNT')]).writeto(output)
    return output.getvalue()


def coverage(folder: Path, manifest):
    rows = []
    for item in manifest.get('frames', []):
        path = folder / 'frames' / f"{item['index']}.npz"
        if not path.exists():
            continue
        with np.load(path) as data:
            if 'wavelength_um' not in data.files:
                continue
            wave = data['wavelength_um']
            good = np.isfinite(wave) & np.isfinite(data['data']) & ~data['saturated']
            rows.append({'index': item['index'], 'visit': item.get('visit'), 'time_utc': item['time_utc'],
                         'image_url': item['image_url'], 'mask_url': item.get('mask_url'), 'data_url': item.get('data_url'),
                         'obs_id': item.get('obs_id'), 'min_um': float(wave[good].min()) if good.any() else None,
                         'max_um': float(wave[good].max()) if good.any() else None,
                         'usable_fraction': float(good.mean())})
    return {'frames': rows, 'detector': manifest['query']['detector'],
            'mode': 'per-pixel wavelength coverage; not nominal 102-channel assignments',
            'unit': 'um', 'nominal_channels_available': False}


def inspect_pixel(folder, manifest, index, x, y):
    frames = manifest.get('frames', [])
    item = next((f for f in frames if f['index'] == index), None)
    if item is None:
        raise ValueError('Frame is unavailable')
    with np.load(folder / 'frames' / f'{index}.npz') as data:
        if not (0 <= y < data['data'].shape[0] and 0 <= x < data['data'].shape[1]):
            raise ValueError('Pixel is outside the native grid')
        def number(name):
            if name not in data.files:
                return None
            value = float(data[name][y, x])
            return value if math.isfinite(value) else None
        bits = int(data['flags'][y, x]) if 'flags' in data.files else None
        covered = bool(data['flags_covered'][y, x]) if 'flags_covered' in data.files else None
        definitions = item.get('flag_definitions', {})
        flags = [name for key, name in definitions.items() if bits is not None and bits & (1 << int(key[4:]))]
        sky = WCS(manifest['grid']['header']).pixel_to_world(x, y)
        return {'x': x, 'y': y, 'ra_deg': float(sky.ra.deg), 'dec_deg': float(sky.dec.deg),
                'value': number('data'), 'variance': number('variance'), 'unit': manifest['processing']['unit'],
                'wavelength_um': number('wavelength_um'), 'bandwidth_um': number('bandwidth_um'),
                'flags': flags, 'raw_flags': bits, 'covered': covered,
                'saturated': bool(data['saturated'][y, x]),
                'reason': 'No valid measurement after quality policy' if number('data') is None else 'Available',
                'obs_id': item.get('obs_id'), 'time_utc': item['time_utc']}


def aperture_spectrum(folder, manifest, x, y, visit, radius=2., inner=3., outer=5.):
    if not all(math.isfinite(v) for v in (x, y, radius, inner, outer)) or not (0 < radius < inner < outer <= 12):
        raise ValueError('Require 0 < aperture < inner annulus < outer annulus <= 12 pixels')
    grid = WCS(manifest['grid']['header'])
    size = manifest['grid']['size_px']
    if not (0 <= x < size and 0 <= y < size):
        raise ValueError('Position is outside the native grid')
    yy, xx = np.indices((size, size))
    r2 = (xx - x) ** 2 + (yy - y) ** 2
    aperture, annulus = r2 <= radius ** 2, (r2 >= inner ** 2) & (r2 <= outer ** 2)
    ay, ax = np.mgrid[math.floor(y-radius):math.ceil(y+radius)+1, math.floor(x-radius):math.ceil(x+radius)+1]
    full_aperture_pixels = np.count_nonzero((ax-x)**2 + (ay-y)**2 <= radius**2)
    # TAN projection Jacobian: exact solid angle density at each pixel center.
    plane_area = (proj_plane_pixel_area(grid) * u.deg ** 2).to_value(u.sr)
    sky = grid.pixel_to_world(xx, yy)
    center = grid.pixel_to_world(grid.wcs.crpix[0] - 1, grid.wcs.crpix[1] - 1)
    omega = plane_area * np.cos(center.separation(sky).rad) ** 3
    points = []
    for frame in manifest.get('frames', []):
        if frame.get('visit') != visit:
            continue
        with np.load(folder / 'frames' / f"{frame['index']}.npz") as data:
            if 'wavelength_um' not in data.files:
                continue
            valid = np.isfinite(data['data']) & np.isfinite(data['variance']) & (data['variance'] > 0) & ~data['saturated']
            ap, bg = aperture & valid, annulus & valid
            fraction = float(ap.sum() / full_aperture_pixels)
            if fraction < .7 or bg.sum() < 5 or np.any(aperture & data['saturated']):
                continue
            background = float(np.median(data['data'][bg]))
            flux = float(np.sum((data['data'][ap] - background) * omega[ap]) * 1e6)
            error = float(np.sqrt(np.sum(data['variance'][ap] * omega[ap] ** 2)) * 1e6)
            wave = data['wavelength_um'][ap]
            if not np.isfinite(wave).any():
                continue
            points.append({'wavelength_um': float(np.nanmedian(wave)), 'flux': flux, 'uncertainty': error,
                           'usable_aperture_fraction': fraction, 'obs_id': frame.get('obs_id'),
                           'time_utc': frame['time_utc'], 'visit': visit})
    position = grid.pixel_to_world(x, y)
    return {'points': sorted(points, key=lambda p: p['wavelength_um']), 'unit': 'Jy',
            'archive': manifest.get('archive'), 'detector': manifest['query']['detector'],
            'algorithm_version': manifest.get('algorithm_version'),
            'position': {'ra_deg': float(position.ra.deg), 'dec_deg': float(position.dec.deg)},
            'parameters': {'x': x, 'y': y, 'visit': visit, 'radius_px': radius, 'inner_px': inner, 'outer_px': outer},
            'status': 'preliminary_aperture_spectrum',
            'limitations': 'Fixed sky aperture; no PSF/aperture correction. Errors include diagonal variance only, omit resampling covariance and background uncertainty. Individual exposures are not 102 nominal channels; epochs are not merged.'}
