"""Offline, reproducible relative-photocentre experiment on original pixels."""
import json
import numpy as np
from astropy.io import fits
from astropy.coordinates import SkyCoord
from astropy import units as u
from astropy.wcs import WCS

from app.archive import ROOT
from app.preview import unusable_mask
from app.centroid import photocentre,robust_translation


def main():
    folder=ROOT/'data/epsilon-cloud'
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    # Deliberately measure original primary exposures, never rendered/stacked PNGs.
    samples=[]
    for frame in manifest['frames']:
        with np.load(ROOT/frame['section_cache'],allow_pickle=False) as a:
            arrays={k:a[k] for k in a.files}
        wcs=WCS(fits.Header.fromstring(str(arrays['wcs_header'])))
        bad,_=unusable_mask(fits.ImageHDU(arrays['FLAGS'],header=fits.Header.fromstring(str(arrays['flags_header']))))
        samples.append((arrays,wcs,~bad))
    origin=SkyCoord(manifest['query']['ra_deg'],manifest['query']['dec_deg'],unit='deg')
    def measure(sky,radius=3):
        values=[]
        for a,wcs,valid in samples:
            x,y=wcs.world_to_pixel(sky)
            fit=photocentre(a['IMAGE'].astype(float)-a['ZODI'],a['VARIANCE'],valid,float(x),float(y),radius)
            measured=wcs.pixel_to_world(fit['x'],fit['y'])
            east,north=origin.spherical_offsets_to(measured)
            values.append({**fit,'east_arcsec':float(east.arcsec),'north_arcsec':float(north.arcsec),
                           'ra_deg':float(measured.ra.deg),'dec_deg':float(measured.dec.deg)})
        return values,np.array([values[1]['east_arcsec']-values[0]['east_arcsec'],values[1]['north_arcsec']-values[0]['north_arcsec']])
    target,raw=measure(origin)
    a,wcs,valid=samples[0]
    image=a['IMAGE'].astype(float)-a['ZODI']
    background=np.median(image[valid]);yy,xx=np.indices(image.shape)
    peaks=valid&np.isfinite(image)&(a['VARIANCE']>0)&((image-background)>10*np.sqrt(np.maximum(a['VARIANCE'],0)))
    for dy in [-1,0,1]:
        for dx in [-1,0,1]:
            if dy or dx:peaks &= image>np.roll(np.roll(image,dy,axis=0),dx,axis=1)
    tx,ty=wcs.world_to_pixel(origin)
    peaks &= (xx>8)&(yy>8)&(xx<image.shape[1]-9)&(yy<image.shape[0]-9)&(np.hypot(xx-tx,yy-ty)>7)
    refs=[]
    for py,px in zip(*np.where(peaks)):
        sky=wcs.pixel_to_world(int(px),int(py))
        try:
            fits_,shift=measure(sky)
            if any(np.hypot(f['x']-px,f['y']-py)>4 for f in fits_[:1]):continue
            refs.append({'initial_pixel':[int(px),int(py)],'measurements':fits_,'offset_arcsec':shift.tolist()})
        except ValueError:
            continue
    if refs:
        translation,keep=robust_translation([r['offset_arcsec'] for r in refs])
        residual=np.array([r['offset_arcsec'] for r,k in zip(refs,keep) if k])-translation
        scatter=np.std(residual,axis=0,ddof=1) if keep.sum()>1 else np.array([np.nan,np.nan])
        for r,k in zip(refs,keep):r['used']=bool(k)
    else:
        translation=np.zeros(2);keep=np.array([],dtype=bool);scatter=np.array([np.nan,np.nan])
    corrected=raw-translation
    sensitivity=[]
    for radius in [2.5,3.,3.5]:
        try:
            _,shift=measure(origin,radius)
            sensitivity.append({'radius_pixel':radius,'raw_shift_arcsec':shift.tolist()})
        except ValueError as e:sensitivity.append({'radius_pixel':radius,'error':str(e)})
    result={'method':'signed-flux aperture photocentre on primary native IMAGE-ZODI; annular median background',
            'dates':[f['time_utc'] for f in manifest['frames']],
            'input_sections':[f['section_cache'] for f in manifest['frames']],
            'target_measurements':target,'raw_shift_east_north_arcsec':raw.tolist(),
            'reference_sources':refs,'reference_count_used':int(keep.sum()),
            'field_translation_east_north_arcsec':translation.tolist(),
            'relative_shift_east_north_arcsec':corrected.tolist(),
            'relative_shift_length_arcsec':float(np.linalg.norm(corrected)),
            'reference_scatter_arcsec':[float(x) if np.isfinite(x) else None for x in scatter],
            'aperture_sensitivity':sensitivity,
            'status':'exploratory_not_confirmed',
            'conclusion':'Photocentre displacement measured; reliable motion confirmation still requires validated PSF astrometry and reference-source checks.',
            'limitations':['Reference candidates are image peaks, not Gaia-verified stationary stars.',
                           'Pixel-noise uncertainties exclude PSF, background, masks and WCS systematics.',
                           'No observer-parallax correction or PSF matching; no detection significance is claimed.',
                           'Only primary exposures are measured; display epoch stacks are not measurement inputs.']}
    (folder/'motion-report.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    lines=['# Epsilon Indi B — измерение фотоцентра','',f"Даты: {' / '.join(result['dates'])}",'',
           f"Сырое смещение (восток, север): {raw.round(3).tolist()} угл. сек.",
           f"Опорных кандидатов использовано: {int(keep.sum())}.",
           f"После поправки на сдвиг поля: {corrected.round(3).tolist()} угл. сек.",
           f"Длина относительного смещения: {np.linalg.norm(corrected):.3f} угл. сек.",'',
           '**Это экспериментальное измерение фотоцентра, не подтверждение собственного движения.**','',
           'Измерены исходные пиксели основных экспозиций. Круг и PNG не используются.','',
           '## Ограничения','']+['- '+x for x in result['limitations']]
    (ROOT/'docs/epsilon-motion-result.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['raw_shift_east_north_arcsec','reference_count_used','relative_shift_east_north_arcsec','relative_shift_length_arcsec','aperture_sensitivity']},indent=2))


if __name__=='__main__':main()
