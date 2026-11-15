"""Bounded, cached TAP catalogue context on the numerical SPHEREx grid."""
import csv
import functools
import io
import math
import time

import requests
from astropy.coordinates import SkyCoord
from astropy.time import Time
from astropy.wcs import WCS

from app.astrometry import propagate

LIMIT = 1000
SERVICES = {
    'gaia': ('https://gea.esac.esa.int/tap-server/tap/sync', 'gaiadr3.gaia_source',
             'source_id,ra,dec,ref_epoch,pmra,pmdec,parallax,ruwe,phot_g_mean_mag'),
    'wise': ('https://irsa.ipac.caltech.edu/TAP/sync', 'allwise_p3as_psd',
             'designation,ra,dec,w1mpro,cc_flags,ph_qual'),
}


class CatalogError(Exception):
    pass


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


@functools.lru_cache(maxsize=128)
def _query(catalog, ra, dec, radius, hour):
    url, table, columns = SERVICES[catalog]
    query = (f"SELECT TOP {LIMIT + 1} {columns} FROM {table} WHERE "
             f"1=CONTAINS(POINT('ICRS',ra,dec),CIRCLE('ICRS',{ra},{dec},{radius}))")
    try:
        response = requests.get(url, params={'REQUEST':'doQuery','LANG':'ADQL','FORMAT':'csv','QUERY':query}, timeout=(5, 20))
        response.raise_for_status()
        reader = csv.DictReader(io.StringIO(response.text))
        if not reader.fieldnames or not {'ra', 'dec'}.issubset(reader.fieldnames):
            raise CatalogError('TAP returned no valid catalogue table')
        return list(reader)
    except requests.RequestException as error:
        raise CatalogError(f'{catalog} catalogue service unavailable ({type(error).__name__})') from error


def overlay(manifest, index, catalog):
    if catalog not in SERVICES:
        raise ValueError('Catalogue must be gaia or wise')
    frame = next((f for f in manifest['frames'] if f['index'] == index), None)
    if frame is None:
        raise ValueError('Choose an available exposure')
    grid = WCS(manifest['grid']['header'])
    ra, dec = manifest['query']['ra_deg'], manifest['query']['dec_deg']
    # Extra Gaia margin admits sources that moved into the field since J2016.
    radius = manifest['query']['fov_deg'] * .72 + (.05 if catalog == 'gaia' else 0)
    rows = _query(catalog, ra, dec, radius, int(time.time() // 3600))
    epoch = float(Time(frame['time_utc'].replace('Z', ''), scale='utc').jyear)
    sources = []
    for row in rows[:LIMIT]:
        lon, lat = number(row.get('ra')), number(row.get('dec'))
        if lon is None or lat is None:
            continue
        ref_epoch = number(row.get('ref_epoch')) if catalog == 'gaia' else None
        pmra, pmdec = number(row.get('pmra')), number(row.get('pmdec'))
        moved = catalog == 'gaia' and None not in (ref_epoch, pmra, pmdec)
        if moved:
            position = propagate(lon, lat, pmra, pmdec, ref_epoch, epoch)
            lon, lat = position['ra_deg'], position['dec_deg']
        x, y = grid.world_to_pixel(SkyCoord(lon, lat, unit='deg'))
        size = manifest['grid']['size_px']
        if not (math.isfinite(x) and math.isfinite(y) and -.5 <= x < size-.5 and -.5 <= y < size-.5):
            continue
        sources.append({'id': row.get('source_id') or row.get('designation'), 'catalog': catalog,
                        'ra_deg': lon, 'dec_deg': lat, 'grid_x': float(x), 'grid_y': float(y),
                        'reference_epoch': ref_epoch, 'observation_epoch': epoch,
                        'proper_motion_applied': moved, 'pmra_mas_yr': pmra, 'pmdec_mas_yr': pmdec,
                        'ruwe': number(row.get('ruwe')), 'cc_flags': row.get('cc_flags'),
                        'ph_qual': row.get('ph_qual'), 'magnitude': number(row.get('phot_g_mean_mag') or row.get('w1mpro'))})
    return {'catalog': 'Gaia DR3' if catalog == 'gaia' else 'AllWISE', 'sources': sources,
            'truncated': len(rows) > LIMIT, 'row_limit': LIMIT, 'source': SERVICES[catalog][0],
            'coordinate_frame': 'ICRS', 'proper_motion_unit': 'mas/yr',
            'limitations': 'Catalogue markers are not SPHEREx detections. Gaia propagation is linear without observer parallax or radial velocity. Missing motion stays unknown. AllWISE positions are unpropagated; the precise reference epoch is unavailable here. The query has a finite proper-motion margin.'}
