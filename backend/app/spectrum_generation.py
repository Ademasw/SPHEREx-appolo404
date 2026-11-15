"""Adapt hacaton's progressive D1-D6 spectrum to immutable numeric generations."""
from astropy.time import Time
from app.inspector import aperture_spectrum
from app.stack import group_epochs


def generate(info, fov, background, clean, smooth, jobs, pipeline):
    points, done, pending, errors, provenance = [], [], [], {}, {}
    active = 0
    for det in pipeline.DETECTORS:
        manifest = pipeline.load(info['ra_deg'], info['dec_deg'], det, fov, background, clean, smooth)
        if manifest is None or jobs._stale(manifest):
            if active >= 2:
                pending.append(det)
                continue
            state = jobs.request(info['ra_deg'], info['dec_deg'], det, fov,
                                 background=background, clean=clean, smooth=smooth, target=None)
            if state['status'] == 'error':
                errors[det] = state['error']
                continue
            if state['status'] != 'done':
                active += 1
                pending.append(det)
                continue
            manifest = state['manifest']
        try:
            key = manifest['query']['key']
            folder = pipeline.product_dir(key, det, manifest.get('generation'))
            center = (manifest['grid']['size_px'] - 1) / 2
            for visit in dict.fromkeys(frame.get('visit') for frame in manifest['frames']):
                result = aperture_spectrum(folder, manifest, center, center, visit, radius=2, inner=4, outer=7)
                for point in result['points']:
                    points.append({**point, 'detector': det, 'flux_ujy': point['flux'] * 1e6,
                                   'err_ujy': point['uncertainty'] * 1e6, 'saturated': False})
            done.append(det)
            provenance[det] = {'archive': manifest.get('archive'), 'generation':manifest.get('generation'),
                               'algorithm_version':manifest.get('algorithm_version')}
        except (ValueError, KeyError, OSError) as error:
            errors[det] = f'Numerical spectrum unavailable: {error}'
    if points:
        times = [Time(point['time_utc'].removesuffix('Z'), format='isot').mjd for point in points]
        for epoch, members in enumerate(group_epochs(times)):
            for index in members:
                points[index]['epoch'] = epoch
    points.sort(key=lambda p:(p['wavelength_um'],p['time_utc']))
    return {'status':'running' if pending else 'done', 'resolved':info, 'points':points,
            'detectors_done':done,'detectors_pending':pending,'errors':errors,'provenance':provenance,
            'unit':'uJy','parameters':{'fov_deg':fov,'background':background,'clean':clean,'smooth':smooth,
                                      'radius_px':2,'inner_px':4,'outer_px':7,'aperture':'fixed sky position'},
            'note':'Quick-look aperture spectrum from real observations, not simulated data. Saturated or poorly covered apertures are omitted. No PSF/aperture correction; errors omit background uncertainty and resampling covariance. Different epochs are coloured separately; nearby sources may blend.'}
