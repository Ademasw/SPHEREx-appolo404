"""Cross-match reference photocentres to Gaia DR3 at the observation epoch."""
import io
import json
from datetime import datetime,timezone

import numpy as np
import requests
from astropy.table import Table
from astropy.coordinates import SkyCoord
from astropy.time import Time
from astropy.io import fits
from astropy.wcs import WCS

from app.archive import ROOT
from app.astrometry import propagate
from app.centroid import robust_translation,photocentre
from app.preview import unusable_mask
from app.source_detection import inspect_source


def main():
    folder=ROOT/'data/epsilon-cloud'
    report=json.loads((folder/'motion-report.json').read_text(encoding='utf-8'))
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    cache=folder/'gaia-dr3.ecsv'
    query=f"""SELECT TOP 2000 source_id,ra,dec,ref_epoch,pmra,pmdec,parallax,ruwe,phot_g_mean_mag
    FROM gaiadr3.gaia_source WHERE 1=CONTAINS(POINT('ICRS',ra,dec),
    CIRCLE('ICRS',{manifest['query']['ra_deg']},{manifest['query']['dec_deg']},0.08))
    AND pmra IS NOT NULL AND pmdec IS NOT NULL"""
    if cache.exists():
        table=Table.read(cache,format='ascii.ecsv')
    else:
        print('Querying ESA Gaia DR3 TAP...',flush=True)
        response=requests.post('https://gea.esac.esa.int/tap-server/tap/sync',
                               data={'REQUEST':'doQuery','LANG':'ADQL','FORMAT':'votable','QUERY':query},timeout=(15,90))
        response.raise_for_status()
        table=Table.read(io.BytesIO(response.content),format='votable')
        table.write(cache,format='ascii.ecsv',overwrite=True)
    for name in table.colnames:
        if name.lower()!=name:table.rename_column(name,name.lower())
    epoch=[float(Time(t,format='isot',scale='utc').jyear) for t in report['dates']]
    predicted=[]
    for row in table:
        predicted.append(propagate(float(row['ra']),float(row['dec']),float(row['pmra']),float(row['pmdec']),float(row['ref_epoch']),epoch[0]))
    if not predicted:raise ValueError('No Gaia sources with proper motion returned')
    sky=SkyCoord([p['ra_deg'] for p in predicted],[p['dec_deg'] for p in predicted],unit='deg')
    matches=[]
    for ref in report['reference_sources']:
        measured=ref['measurements'][0]
        source=SkyCoord(measured['ra_deg'],measured['dec_deg'],unit='deg')
        distances=source.separation(sky).arcsec
        order=np.argsort(distances);idx=int(order[0]);row=table[idx]
        nearest=float(distances[idx]);second=float(distances[order[1]]) if len(order)>1 else None
        ruwe=None if np.ma.is_masked(row['ruwe']) else float(row['ruwe'])
        accepted=nearest<=2.0 and (second is None or second>3.0) and ruwe is not None and ruwe<1.4
        dt=epoch[1]-epoch[0]
        expected=np.array([float(row['pmra']),float(row['pmdec'])])*dt/1000.
        # Subtract catalog motion of reference before estimating the instrument shift.
        residual=np.array(ref['offset_arcsec'])-expected
        matches.append({'initial_pixel':ref['initial_pixel'],'gaia_source_id':str(row['source_id']),
                        'separation_arcsec':nearest,'second_nearest_arcsec':second,'ruwe':ruwe,
                        'g_mag':float(row['phot_g_mean_mag']),'accepted':bool(accepted),
                        'pmra_mas_year':float(row['pmra']),'pmdec_mas_year':float(row['pmdec']),
                        'expected_motion_east_north_arcsec':expected.tolist(),
                        'instrument_shift_candidate_arcsec':residual.tolist()})
    ids=[m['gaia_source_id'] for m in matches if m['accepted']]
    if len(ids)!=len(set(ids)):
        for m in matches:
            if ids.count(m['gaia_source_id'])>1:m['accepted']=False
    accepted=[m for m in matches if m['accepted']]
    # Independently look for usable catalog stars throughout the original sections.
    samples=[]
    origin=SkyCoord(manifest['query']['ra_deg'],manifest['query']['dec_deg'],unit='deg')
    for frame in manifest['frames']:
        with np.load(ROOT/frame['section_cache'],allow_pickle=False) as stored:a={k:stored[k] for k in stored.files}
        w=WCS(fits.Header.fromstring(str(a['wcs_header'])))
        bad,_=unusable_mask(fits.ImageHDU(a['FLAGS'],header=fits.Header.fromstring(str(a['flags_header']))))
        samples.append((a,w,~bad))
    catalog_refs=[]
    for idx,row in enumerate(table):
        if np.ma.is_masked(row['ruwe']) or float(row['ruwe'])>=1.4:continue
        candidate=sky[idx]
        if origin.separation(candidate).arcsec<40:continue
        if sum(candidate.separation(sky).arcsec<3)>1:continue
        measurements=[]
        try:
            for a,w,valid in samples:
                x,y=w.world_to_pixel(candidate)
                if not (8<x<a['IMAGE'].shape[1]-9 and 8<y<a['IMAGE'].shape[0]-9):raise ValueError('Edge')
                image=a['IMAGE'].astype(float)-a['ZODI']
                check=inspect_source(image,a['VARIANCE'],valid,float(x),float(y))
                if check.get('status')!='signal_candidate' or check['peak_pixel_snr']<10:raise ValueError('Weak')
                fit=photocentre(image,a['VARIANCE'],valid,float(x),float(y))
                measured=w.pixel_to_world(fit['x'],fit['y'])
                measurements.append(measured)
            separation=float(candidate.separation(measurements[0]).arcsec)
            if separation>2:continue
            east,north=measurements[0].spherical_offsets_to(measurements[1])
            expected=np.array([float(row['pmra']),float(row['pmdec'])])*(epoch[1]-epoch[0])/1000
            catalog_refs.append({'gaia_source_id':str(row['source_id']),'separation_arcsec':separation,
                                 'ruwe':float(row['ruwe']),
                                 'instrument_shift_candidate_arcsec':(np.array([east.arcsec,north.arcsec])-expected).tolist()})
        except ValueError:continue
    result={'catalog':'Gaia DR3','retrieved_at':datetime.now(timezone.utc).isoformat(),'query':query,
            'catalog_rows':len(table),'matches':matches,'accepted_count':len(accepted),
            'criteria':'Nearest epoch-propagated match <=2 arcsec; second nearest >3 arcsec; RUWE <1.4; unique IDs',
            'catalog_reference_candidates':catalog_refs,
            'status':'insufficient_verified_references','limitations':['Reference parallax is not applied; PSF/blending and local distortion remain unchecked.']}
    if len(catalog_refs)>=3:
        offsets=np.array([m['instrument_shift_candidate_arcsec'] for m in catalog_refs])
        translation,keep=robust_translation(offsets)
        corrected=np.array(report['raw_shift_east_north_arcsec'])-translation
        result.update({'status':'catalog_checked_preliminary' if keep.sum()>=3 else 'insufficient_verified_references','reference_count_used':int(keep.sum()),
                       'field_translation_east_north_arcsec':translation.tolist(),
                       'relative_shift_east_north_arcsec':corrected.tolist(),
                       'relative_shift_length_arcsec':float(np.linalg.norm(corrected)),
                       'reference_scatter_arcsec':np.std(offsets[keep]-translation,axis=0,ddof=1).tolist()})
    report['gaia_validation']=result
    (folder/'motion-report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    (folder/'gaia-validation.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    lines=['# Проверка опорных источников по Gaia DR3','',f"Проверено кандидатов: {len(matches)}; принято: {len(accepted)}.",'',
           '| Gaia source_id | Расстояние, ″ | RUWE | Принят |','|---|---:|---:|---|']
    lines += [f"| {m['gaia_source_id']} | {m['separation_arcsec']:.3f} | {m['ruwe']} | {m['accepted']} |" for m in matches]
    lines+=['','Таблица выше относится к первоначальным пиковым кандидатам. Ниже —','финальный независимый поиск опор от координат Gaia на исходных пикселях.','',
            '| Gaia source_id | Расстояние, ″ | RUWE |','|---|---:|---:|']
    lines += [f"| {m['gaia_source_id']} | {m['separation_arcsec']:.3f} | {m['ruwe']:.3f} |" for m in catalog_refs]
    lines+=['',f"Статус: `{result['status']}`.",'','Параллакс, PSF и смешение источников не проверены; подтверждённое движение не заявляется.']
    if 'relative_shift_length_arcsec' in result:lines+=['',f"Смещение после поправки на движения опорных источников: {result['relative_shift_length_arcsec']:.3f}″."]
    (ROOT/'docs/gaia-validation.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
