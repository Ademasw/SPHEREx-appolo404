"""Build a wavelength-selected two-date source view from official cloud sections."""
import hashlib
import json

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
from PIL import Image, ImageDraw

from app.archive import ROOT
from app.preview import align_nearest, make_grid, unusable_mask
from app.source_detection import inspect_source
from app.display import grayscale_rgb
from app.epoch_stack import combine_epoch


def read_section(row, folder, margin=27):
    key=hashlib.sha256((row['cloud_url']+(f':margin={margin}' if margin!=27 else '')).encode()).hexdigest()[:24]
    cache=folder/f'{key}.npz'
    if cache.exists():
        with np.load(cache,allow_pickle=False) as stored:
            return {name:stored[name] for name in stored.files},cache
    with fits.open(row['cloud_url'],use_fsspec=True,fsspec_kwargs={'block_size':65536},memmap=False) as hdus:
        spatial=WCS(hdus['IMAGE'].header,fobj=hdus)
        x,y=row['source_pixel']
        # Wide enough for the rotated 3-arcminute output field plus an annulus.
        x0,x1=max(0,int(x)-margin),min(hdus['IMAGE'].shape[1],int(x)+margin+1)
        y0,y1=max(0,int(y)-margin),min(hdus['IMAGE'].shape[0],int(y)+margin+1)
        region=(slice(y0,y1),slice(x0,x1))
        arrays={name:np.asarray(hdus[name].section[region]) for name in ['IMAGE','FLAGS','VARIANCE','ZODI']}
        yy,xx=np.indices(arrays['IMAGE'].shape)
        zodi_wcs=WCS(hdus['ZODI'].header,fobj=hdus)
        zx,zy=zodi_wcs.world_to_pixel(spatial.pixel_to_world(xx+x0,yy+y0))
        if not (np.allclose(zx,xx+x0,atol=.01) and np.allclose(zy,yy+y0,atol=.01)):
            raise ValueError('ZODI grid mismatch')
        spectral=WCS(hdus['IMAGE'].header,fobj=hdus,key='W')
        spectral.sip=None
        wave,_=spectral.pixel_to_world(xx+x0,yy+y0)
        arrays.update({'wavelength_um':wave.to_value('um'),
                       'wcs_header':np.array(spatial.slice(region).to_header(relax=True).tostring()),
                       'original_image_header':np.array(hdus['IMAGE'].header.tostring()),
                       'flags_header':np.array(hdus['FLAGS'].header.tostring()),
                       'source_pixel':np.array([x-x0,y-y0]),'origin_xy':np.array([x0,y0])})
        np.savez_compressed(cache,**arrays)
        return arrays,cache


def main():
    folder=ROOT/'data/epsilon-cloud'
    rows=json.loads((folder/'spectral-probe.json').read_text(encoding='utf-8'))
    early=[r for r in rows if 'error' not in r and r['t_min']<61041]
    late=[r for r in rows if 'error' not in r and r['t_min']>=61041]
    pairs=[(abs(a['wavelength_um']-b['wavelength_um']),a,b) for a in early for b in late]
    def members(row):
        tolerance=.25*row['bandwidth_um']
        return [r for r in rows if 'error' not in r and abs(r['t_min']-row['t_min'])<=7
                and abs(r['wavelength_um']-row['wavelength_um'])<=tolerance]
    pairs=[p for p in pairs if p[0]<=.25*min(p[1]['bandwidth_um'],p[2]['bandwidth_um'])]
    if not pairs:
        raise ValueError('No spectrally compatible pairs')
    # Prefer a band with real repeat coverage, then the smallest spectral difference.
    _,a,b=min(pairs,key=lambda p:(-len(members(p[1]))-len(members(p[2])),p[0]))
    tolerance=.25*min(a['bandwidth_um'],b['bandwidth_um'])
    if abs(a['wavelength_um']-b['wavelength_um'])>tolerance:
        raise ValueError('No sufficiently wavelength-matched pair among probed observations')
    audit=json.loads((ROOT/'data/catalog/audit.json').read_text(encoding='utf-8'))
    target=next(t for t in audit['targets'] if t['id']=='epsilon-indi-b')
    center=target['search_position']
    grid,size=make_grid(center['ra_deg'],center['dec_deg'],fov_deg=.05)
    aligned,wave_maps,frames=[],[],[]
    for i,row in enumerate([a,b]):
        print(f"Reading cloud section {i+1}/2; lambda={row['wavelength_um']:.6f} um",flush=True)
        arrays,cache=read_section(row,folder)
        spatial=WCS(fits.Header.fromstring(str(arrays['wcs_header'])))
        flag_hdu=fits.ImageHDU(arrays['FLAGS'],header=fits.Header.fromstring(str(arrays['flags_header'])))
        bad,flags_used=unusable_mask(flag_hdu)
        check=inspect_source(arrays['IMAGE'],arrays['VARIANCE'],~bad,*arrays['source_pixel'])
        if check['status']!='signal_candidate':
            raise ValueError(f'Source quality check failed: {check}')
        residual=arrays['IMAGE'].astype(float)-arrays['ZODI']
        primary=align_nearest(residual,spatial,grid,size,~bad)
        primary_variance=align_nearest(arrays['VARIANCE'],spatial,grid,size,~bad)
        reference_wave=align_nearest(arrays['wavelength_um'],spatial,grid,size)
        image_members=[primary]
        variance_members=[primary_variance]
        wavelength_members=[reference_wave]
        contributors=[{'obs_id':row['obs_id'],'time_utc':Time(row['t_min'],format='mjd').isot,
                       'cloud_url':row['cloud_url'],'section_cache':str(cache.relative_to(ROOT))}]
        for donor in members(row):
            if donor['obs_id']==row['obs_id']:
                continue
            print(f"Reading repeat {donor['obs_id']} to replace invalid pixels with real data",flush=True)
            da,dcache=read_section(donor,folder)
            dw=WCS(fits.Header.fromstring(str(da['wcs_header'])))
            dbad,_=unusable_mask(fits.ImageHDU(da['FLAGS'],header=fits.Header.fromstring(str(da['flags_header']))))
            image_members.append(align_nearest(da['IMAGE'].astype(float)-da['ZODI'],dw,grid,size,~dbad))
            variance_members.append(align_nearest(da['VARIANCE'],dw,grid,size,~dbad))
            wavelength_members.append(align_nearest(da['wavelength_um'],dw,grid,size))
            contributors.append({'obs_id':donor['obs_id'],'time_utc':Time(donor['t_min'],format='mjd').isot,
                                 'cloud_url':donor['cloud_url'],'section_cache':str(dcache.relative_to(ROOT)),
                                 'section_sha256':hashlib.sha256(dcache.read_bytes()).hexdigest()})
        epoch,counts=combine_epoch(image_members,variance_members,wavelength_members,reference_wave,tolerance)
        aligned.append(epoch)
        wave_maps.append(reference_wave)
        position=row['predicted_position']
        gx,gy=grid.world_to_pixel(SkyCoord(position['ra_deg'],position['dec_deg'],unit='deg'))
        frames.append({'index':i,'observation':{'obs_id':row['obs_id'],'t_min':row['t_min'],'access_url':row['access_url']},
                       'time_utc':Time(row['t_min'],format='mjd').isot,
                       'center_wavelength_um':row['wavelength_um'],'center_bandwidth_um':row['bandwidth_um'],
                       'cutout_url':row['access_url'],'cloud_url':row['cloud_url'],
                       'section_cache':str(cache.relative_to(ROOT)),
                       'section_sha256':hashlib.sha256(cache.read_bytes()).hexdigest(),
                       'predicted_grid_pixel':[float(gx),float(gy)],'source_check':check,'masked_flags':flags_used,
                       'contributors':contributors,'epoch_member_count':len(contributors),
                       'gaps_filled_from_repeats':int((~np.isfinite(primary)&np.isfinite(epoch)).sum()),
                       'image_url':f'/api/epsilon/frames/{i}'})
    common=np.isfinite(aligned[0]) & np.isfinite(aligned[1]) & (np.abs(wave_maps[0]-wave_maps[1])<=tolerance)
    if common.mean()<.5:
        raise ValueError('Insufficient spectrally comparable common coverage')
    aligned=[np.where(common,array,np.nan) for array in aligned]
    low,high=np.nanpercentile(np.stack(aligned),[5,99.5])
    sheet=Image.new('RGB',(900,530),'#101827')
    rendered=[]
    for i,(array,frame) in enumerate(zip(aligned,frames)):
        rgb=grayscale_rgb(array,common,low,high)
        canvas=Image.new('RGB',(450,530),'#101827')
        canvas.paste(Image.fromarray(np.flipud(rgb)).resize((420,420),Image.Resampling.NEAREST),(15,75))
        draw=ImageDraw.Draw(canvas)
        draw.text((15,12),'Epsilon Indi B | SPHEREx DR1 D3',fill='white')
        draw.text((15,32),frame['time_utc'][:19]+f" UTC | {frame['epoch_member_count']} exposure(s)",fill='white')
        draw.text((15,52),f"Wavelength at prediction: {frame['center_wavelength_um']:.5f} um",fill='white')
        # Fixed reference marker: same sky coordinates on both images, never animated by prediction.
        cx,cy=225,285
        draw.ellipse((cx-35,cy-35,cx+35,cy+35),outline='#ff9c66',width=2)
        draw.text((15,507),'Fixed sky marker | shared scale | motion unconfirmed',fill='#ffbd96')
        canvas.save(folder/f'{i}.png')
        mask_canvas=canvas.copy()
        mask_canvas.paste(Image.fromarray(np.flipud(grayscale_rgb(array,common,low,high,True))).resize((420,420),Image.Resampling.NEAREST),(15,75))
        ImageDraw.Draw(mask_canvas).ellipse((cx-35,cy-35,cx+35,cy+35),outline='#ff9c66',width=2)
        mask_canvas.save(folder/f'{i}-mask.png')
        sheet.paste(canvas,(i*450,0))
        rendered.append(canvas)
        frame['usable_grid_fraction']=float(common.mean())
    sheet.save(folder/'comparison.png')
    rendered[0].save(folder/'blink.gif',save_all=True,append_images=rendered[1:],duration=1000,loop=0)
    positions=[SkyCoord(r['predicted_position']['ra_deg'],r['predicted_position']['dec_deg'],unit='deg') for r in [a,b]]
    expected=float(positions[0].separation(positions[1]).arcsec)
    result={'target_name':'Epsilon Indi B field','detector':'D3',
            'field_note':'Compact infrared source near the catalog position. The orange marker stays fixed on the sky in both frames.',
            'query':{'ra_deg':center['ra_deg'],'dec_deg':center['dec_deg'],'release':'dr1'},
            'grid':{'fov_deg':.05,'pixel_arcsec':6.2,'orientation':'north up, east left'},
            'mode_note':'Close wavelengths and a shared scale. Valid repeats within 7 days are combined using inverse pixel variance. The separate photocentre experiment is preliminary.',
            'frames':frames,'predicted_motion_arcsec':expected,
            'processing':{'background':'IMAGE - ZODI after spatial grid verification','shared_valid_fraction':float(common.mean()),
                          'mask_overlay_available':True,'missing_pixels':int((~common).sum()),
                          'missing_display':'neutral gray checkerboard; amber when quality overlay enabled',
                          'gap_interpolation':'none; missing measurements remain invalid',
                          'epoch_combination':'inverse pixel-variance weights after nearest-neighbor spatial resampling',
                          'epoch_window_days':7,
                          'display_low':float(low),'display_high':float(high),'wavelength_tolerance_um':tolerance,
                          'marker':'fixed at J2026 search center; not moved with catalog prediction'},
            'warnings':['A strong local signal is present near each predicted position; this is a diagnostic source association, not a discovery.',
                        'The orange ring is fixed at the same sky coordinates. Its position is not an image measurement.',
                        'Peak-pixel S/N uses supplied per-pixel variance and annular background; it is not integrated source significance.',
                        'Repeat exposures within 7 days are combined where wavelengths agree; no observations from another year fill gaps. Effective PSF and resampling covariance are not modeled.',
                        f'Expected proper-motion displacement is {expected:.2f} arcsec, calculated from the catalog and not measured here.',
                        'No PSF matching, field-star astrometric registration or observer-parallax correction; movement remains unconfirmed.']}
    (folder/'manifest.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'dates':[f['time_utc'] for f in frames],'wavelengths':[f['center_wavelength_um'] for f in frames],
                      'checks':[f['source_check'] for f in frames],'common_fraction':float(common.mean())}),flush=True)


if __name__=='__main__':
    main()
