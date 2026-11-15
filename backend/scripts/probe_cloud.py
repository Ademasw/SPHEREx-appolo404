"""Read official cloud FITS headers/WCS to select wavelengths before cutouts."""
import json
from concurrent.futures import ThreadPoolExecutor

from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
from astropy import units as u
from astroquery.ipac.irsa import Irsa

from app.archive import ROOT
from app.astrometry import propagate


def cloud_url(info):
    cloud = json.loads(info)['aws']
    if cloud['bucket_name'] != 'nasa-irsa-spherex' or not cloud['key'].startswith(('dr1/','qr3/')) or '..' in cloud['key']:
        raise ValueError('Unexpected cloud product')
    return f"https://{cloud['bucket_name']}.s3.{cloud['region']}.amazonaws.com/{cloud['key']}"


def main():
    audit=json.loads((ROOT/'data/catalog/audit.json').read_text(encoding='utf-8'))
    target=next(t for t in audit['targets'] if t['id']=='epsilon-indi-b')
    center=target['search_position']
    rows=Irsa.query_sia(pos=(SkyCoord(center['ra_deg'],center['dec_deg'],unit='deg'),1*u.arcsec),collection=['spherex_dr1'])
    rows=rows[rows['energy_bandpassname']=='SPHEREx-D3']
    rows.sort('t_min')
    output=ROOT/'data/epsilon-cloud'
    output.mkdir(parents=True,exist_ok=True)
    # A few first-epoch scan positions, plus first observation of the latest epoch.
    selected=list(range(len(rows)))
    cache_file=output/'spectral-probe.json'
    cached={r['obs_id']:r for r in json.loads(cache_file.read_text(encoding='utf-8')) if 'error' not in r} if cache_file.exists() else {}
    def inspect(index):
        row=rows[index]
        if str(row['obs_id']) in cached:
            return cached[str(row['obs_id'])]
        result={'index':index,'obs_id':str(row['obs_id']),'t_min':float(row['t_min']),
                'access_url':str(row['access_url']),'cloud_url':cloud_url(str(row['cloud_access']))}
        try:
            cat=target['catalog']
            position=propagate(cat['ra'],cat['dec'],cat['pmra'],cat['pmdec'],2000.,float(Time(result['t_min'],format='mjd').jyear))
            with fits.open(result['cloud_url'],use_fsspec=True,fsspec_kwargs={'block_size':65536},memmap=False) as hdus:
                spatial=WCS(hdus['IMAGE'].header,fobj=hdus)
                x,y=spatial.world_to_pixel(SkyCoord(position['ra_deg'],position['dec_deg'],unit='deg'))
                spectral=WCS(hdus['IMAGE'].header,fobj=hdus,key='W')
                spectral.sip=None
                wave,bw=spectral.pixel_to_world(x,y)
                result.update({'wavelength_um':float(wave.to_value('um')),'bandwidth_um':float(bw.to_value('um')),
                               'source_pixel':[float(x),float(y)],'predicted_position':position})
        except Exception as error:
            result['error']=f'{type(error).__name__}: {error}'
        print(json.dumps(result),flush=True)
        return result
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(inspect,selected))
    (output/'spectral-probe.json').write_text(json.dumps(results,indent=2,allow_nan=False),encoding='utf-8')


if __name__=='__main__':
    main()
