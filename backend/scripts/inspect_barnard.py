"""Inspect actual source neighborhoods before claiming a useful blink pair."""
import hashlib
import json
import argparse
from urllib.parse import urlencode

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
from PIL import Image, ImageDraw
import requests

from app.archive import ROOT
from app.astrometry import propagate
from app.preview import align_nearest, make_grid, unusable_mask
from app.source_detection import inspect_source
from app.display import grayscale_rgb
from scripts.prepare_preview import download


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--late-first', action='store_true', help='Use first observation after largest temporal gap')
    parser.add_argument('--detector', choices=['D1', 'D3'])
    parser.add_argument('--target', choices=['barnard', 'epsilon-indi-b', 'wise-0855', 'rw-aur', 'r-dra'], default='barnard')
    parser.add_argument('--early-index', type=int, default=0)
    parser.add_argument('--cached-only', action='store_true')
    args = parser.parse_args()
    audit = json.loads((ROOT / 'data/catalog/audit.json').read_text(encoding='utf-8'))
    target = next(item for item in audit['targets'] if item['id'] == args.target)
    report = json.loads((ROOT / target['coverage']['report_path']).read_text(encoding='utf-8'))
    catalog = target['catalog']
    center = target['search_position']
    grid, size = make_grid(center['ra_deg'], center['dec_deg'], fov_deg=0.05)
    output = ROOT / ('data/barnard-matched' if args.late_first else 'data/barnard')
    if args.target != 'barnard':
        output = ROOT / 'data/inspections' / args.target
    output.mkdir(parents=True, exist_ok=True)
    raw = ROOT / 'data/cutouts'
    raw.mkdir(parents=True, exist_ok=True)
    rows = []
    for detector in ([f'SPHEREx-{args.detector}'] if args.detector else ['SPHEREx-D1', 'SPHEREx-D3']):
        choices = sorted([r for r in report['observations'] if r['energy_bandpassname'] == detector], key=lambda r: r['t_min'])
        late = int(np.argmax(np.diff([r['t_min'] for r in choices]))) + 1
        if not 0 <= args.early_index < late:
            raise ValueError('early-index must be before the largest epoch gap')
        rows.extend([choices[args.early_index], choices[late] if args.late_first else choices[-2]])
    results = []
    failures = []
    sheet = Image.new('RGB', (840, 520*int(np.ceil(len(rows)/2))), '#101827')
    for index, row in enumerate(rows):
        print(f"Inspecting {index+1}/{len(rows)} {row['energy_bandpassname']}...", flush=True)
        url = row['access_url'] + '?' + urlencode({'center': f"{center['ra_deg']},{center['dec_deg']}", 'size':'0.05'})
        path = raw / (hashlib.sha256(url.encode()).hexdigest()[:24] + '.fits')
        if args.cached_only and not path.exists():
            print('Skipping uncached observation in offline mode',flush=True)
            continue
        try:
            download(url, path)
        except (requests.RequestException, OSError, ValueError) as error:
            failures.append({'observation': row, 'cutout_url': url,
                             'error': f'{type(error).__name__}: {error}'})
            (output/'failures.json').write_text(json.dumps(failures,indent=2),encoding='utf-8')
            print(f'Could not inspect this observation: {error}',flush=True)
            continue
        position = propagate(catalog['ra'], catalog['dec'], catalog['pmra'], catalog['pmdec'], 2000., float(Time(row['t_min'], format='mjd').jyear))
        with fits.open(path) as hdus:
            image = hdus['IMAGE'].data.astype(float)
            spatial = WCS(hdus['IMAGE'].header, fobj=hdus)
            sx, sy = spatial.world_to_pixel(SkyCoord(position['ra_deg'], position['dec_deg'], unit='deg'))
            spectral = WCS(hdus['IMAGE'].header, fobj=hdus, key='W')
            spectral.sip = None
            wave, bw = spectral.pixel_to_world(sx, sy)
            bad, used = unusable_mask(hdus['FLAGS'])
            source_check = inspect_source(image,hdus['VARIANCE'].data,~bad,float(sx),float(sy))
            aligned = align_nearest(image, spatial, grid, size, ~bad)
            gx, gy = grid.world_to_pixel(SkyCoord(position['ra_deg'], position['dec_deg'], unit='deg'))
            yy, xx = np.indices(image.shape)
            nearby = (xx-sx)**2 + (yy-sy)**2 <= 3**2
            flag_values = hdus['FLAGS'].data
            flag_counts = {}
            for key in hdus['FLAGS'].header:
                if key.startswith('MSKN'):
                    count = int(np.count_nonzero((flag_values[nearby].astype(np.int64) & (1 << int(key[4:]))) != 0))
                    if count:
                        flag_counts[hdus['FLAGS'].header[key]] = count
            usable = nearby & ~bad & np.isfinite(image)
            background = image[(~nearby) & (~bad) & np.isfinite(image)]
            peak = float(np.max(image[usable])) if usable.any() else None
            median = float(np.median(background)) if background.size else None
            sigma = float(1.4826*np.median(np.abs(background-median))) if background.size else None
            entry = {'render_index':index, 'source_check':source_check, 'observation': row, 'cutout_url':url, 'fits_path':str(path.relative_to(ROOT)),
                     'time_utc':Time(row['t_min'], format='mjd').isot,
                     'predicted_position':position, 'predicted_grid_pixel':[float(gx),float(gy)],
                     'wavelength_um':float(wave.to_value('um')), 'bandwidth_um':float(bw.to_value('um')),
                     'nearby_pixel_count':int(nearby.sum()), 'nearby_usable_count':int(usable.sum()),
                     'nearby_flags':flag_counts, 'peak':peak, 'background_median':median,
                     'background_mad_sigma':sigma, 'unit':hdus['IMAGE'].header.get('BUNIT'),
                     'warning':'Circle is catalog prediction, not measured source centroid. Per-frame stretch for inspection only.'}
            results.append(entry)
            finite = aligned[np.isfinite(aligned)]
            low, high = np.percentile(finite, [5,99.8])
            rgb = grayscale_rgb(aligned,np.isfinite(aligned),low,high)
            canvas = Image.new('RGB',(420,520),'#101827')
            canvas.paste(Image.fromarray(np.flipud(rgb)).resize((400,400),Image.Resampling.NEAREST),(10,85))
            draw = ImageDraw.Draw(canvas)
            draw.text((12,12), f"{target['name']} field | {row['energy_bandpassname']}",fill='white')
            draw.text((12,32), entry['time_utc'][:19]+' UTC',fill='white')
            draw.text((12,52), f"Predicted-position wavelength {entry['wavelength_um']:.5f} um",fill='white')
            cx = 10+(float(gx)+.5)*400/size
            cy = 85+(size-.5-float(gy))*400/size
            draw.ellipse((cx-22,cy-22,cx+22,cy+22),outline='#ff9c66',width=2)
            draw.text((12,496),'Orange circle: predicted position; detection unverified',fill='#ffbb88')
            canvas.save(output/f'inspect-{index}.png')
            sheet.paste(canvas,((index%2)*420,(index//2)*520))
            sheet.save(output/'inspection.png')
            print(json.dumps(entry),flush=True)
        (output/'inspection.json').write_text(json.dumps(results,indent=2,allow_nan=False),encoding='utf-8')
    sheet.save(output/'inspection.png')
    print(output/'inspection.png')
    if not results:
        raise SystemExit('No observations successfully inspected')


if __name__ == '__main__':
    main()
