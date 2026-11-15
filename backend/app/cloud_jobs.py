"""Bounded local processing queue for real coordinate-based SPHEREx requests."""
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
from fastapi import APIRouter,HTTPException
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel,Field,ConfigDict

from app.archive import ROOT,search
from app.display import grayscale_rgb
from app.preview import align_nearest,make_grid,unusable_mask

router=APIRouter(prefix='/api/jobs')
DIRECTORY=ROOT/'data/jobs'
pool=ThreadPoolExecutor(max_workers=2)
capacity=threading.BoundedSemaphore(4)
lock=threading.RLock()
active=set()


class Query(BaseModel):
    model_config=ConfigDict(allow_inf_nan=False,extra='forbid')
    ra:float=Field(ge=0,lt=360)
    dec:float=Field(ge=-90,le=90)
    fov_deg:float=Field(default=.05,ge=.02,le=.1)
    detector:Literal['D1','D2','D3','D4','D5','D6']='D3'
    release:Literal['dr1','qr3']='dr1'


def folder_for(job_id):
    if len(job_id)!=24 or any(c not in '0123456789abcdef' for c in job_id):
        raise HTTPException(404,'Unknown job')
    return DIRECTORY/job_id


def write_state(folder,**state):
    state['updated_at']=time.time()
    with lock:
        temporary=folder/'state.tmp'
        temporary.write_text(json.dumps(state,allow_nan=False),encoding='utf-8')
        temporary.replace(folder/'state.json')


def process(job_id,query):
    folder=folder_for(job_id)
    def progress(value,message):write_state(folder,status='running',progress=value,message=message)
    try:
        progress(5,'Searching official IRSA archive')
        report=search(query.ra,query.dec,query.release)
        (folder/'archive.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        rows=[r for r in report['observations'] if r['energy_bandpassname']==f'SPHEREx-{query.detector}' and r.get('cloud_access')]
        if not rows:raise ValueError('No cloud-accessible observations cover this position in the selected detector/release')
        selected=[rows[i] for i in sorted(set([0,len(rows)//2,len(rows)-1]))]
        grid,size=make_grid(query.ra,query.dec,query.fov_deg)
        arrays=[];frames=[];failures=[]
        from scripts.probe_cloud import cloud_url
        from scripts.prepare_epsilon import read_section
        margin=int(np.ceil(size/np.sqrt(2)))+5
        for i,row in enumerate(selected):
            progress(15+int(65*i/len(selected)),f'Reading observation {i+1}/{len(selected)} from official cloud')
            try:
                url=cloud_url(row['cloud_access'])
                with fits.open(url,use_fsspec=True,fsspec_kwargs={'block_size':65536},memmap=False) as hdus:
                    spatial=WCS(hdus['IMAGE'].header,fobj=hdus)
                    x,y=spatial.world_to_pixel(SkyCoord(query.ra,query.dec,unit='deg'))
                    spectral=WCS(hdus['IMAGE'].header,fobj=hdus,key='W');spectral.sip=None
                    wave,bw=spectral.pixel_to_world(x,y)
                data,cache=read_section({'cloud_url':url,'source_pixel':[float(x),float(y)]},folder,margin)
                spatial=WCS(fits.Header.fromstring(str(data['wcs_header'])))
                bad,_=unusable_mask(fits.ImageHDU(data['FLAGS'],header=fits.Header.fromstring(str(data['flags_header']))))
                aligned=align_nearest(data['IMAGE'].astype(float)-data['ZODI'],spatial,grid,size,~bad)
                if not np.isfinite(aligned).any():raise ValueError('No valid image pixels')
                index=len(frames)
                frames.append({'index':index,'observation':row,'time_utc':Time(row['t_min'],format='mjd').isot,
                               'center_wavelength_um':float(wave.to_value('um')),'center_bandwidth_um':float(bw.to_value('um')),
                               'usable_grid_fraction':float(np.isfinite(aligned).mean()),'cloud_url':url,'cutout_url':row['access_url'],
                               'section_cache':str(cache.relative_to(ROOT)),
                               'image_url':f'/api/jobs/{job_id}/frames/{index}'})
                arrays.append(aligned)
            except Exception as error:
                failures.append({'obs_id':row['obs_id'],'error':f'{type(error).__name__}: {error}'})
        if not frames:raise ValueError('All selected observations failed; retry later or choose another detector')
        progress(90,'Rendering real observations')
        low,high=np.nanpercentile(np.stack(arrays),[2,99.5])
        if high<=low:raise ValueError('No usable display range')
        for i,array in enumerate(arrays):
            Image.fromarray(np.flipud(grayscale_rgb(array,np.isfinite(array),low,high))).resize((472,472),Image.Resampling.BILINEAR).save(folder/f'{i}.png')
        result={'target_name':'Custom sky region','detector':query.detector,
                'query':{'ra_deg':query.ra,'dec_deg':query.dec,'release':query.release},
                'grid':{'fov_deg':query.fov_deg,'pixel_arcsec':6.2},'frames':frames,
                'field_note':'Real archive observations for your coordinates. No target identification or motion is inferred.',
                'mode_note':'Exploratory time sequence. Wavelengths can differ: brightness changes need not be time variability.',
                'archive_count':len(rows),'failed_observations':failures,
                'warnings':['Dates are observation times from IRSA; images are real calibrated data.',
                            'This first custom search samples up to three observations. It does not match wavelengths or measure motion.',
                            'IMAGE-ZODI, selected quality flags, bilinear display resampling and a shared asinh scale are used.',
                            'A fixed coordinate query does not follow a moving source. Detector-edge coverage can be incomplete.']}
        (folder/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
        write_state(folder,status='complete',progress=100,message=f'{len(frames)} observations ready',result_url=f'/api/jobs/{job_id}/result')
    except Exception as error:
        write_state(folder,status='failed',progress=100,message=str(error))
    finally:
        with lock:active.discard(job_id)
        capacity.release()


@router.post('')
def create(query:Query):
    job_id=hashlib.sha256(query.model_dump_json().encode()).hexdigest()[:24]
    folder=folder_for(job_id)
    with lock:
        if job_id in active:return {'job_id':job_id,'cached':False}
        if (folder/'result.json').exists() and time.time()-(folder/'result.json').stat().st_mtime<86400:
            return {'job_id':job_id,'cached':True}
        if not capacity.acquire(blocking=False):raise HTTPException(429,'Processing queue is full; retry shortly')
        try:
            folder.mkdir(parents=True,exist_ok=True)
            write_state(folder,status='queued',progress=0,message='Queued')
            active.add(job_id);pool.submit(process,job_id,query)
        except Exception:
            active.discard(job_id);capacity.release();raise
    return {'job_id':job_id,'cached':False}


@router.get('/{job_id}')
def state(job_id:str):
    folder=folder_for(job_id);path=folder/'state.json'
    if not path.exists():raise HTTPException(404,'Unknown job')
    with lock:
        data=json.loads(path.read_text(encoding='utf-8'))
        if data['status'] in ['queued','running'] and job_id not in active:
            data.update(status='failed',message='Server restarted during processing; submit the request again')
    return data


@router.get('/{job_id}/result')
def result(job_id:str):
    path=folder_for(job_id)/'result.json'
    if not path.exists():raise HTTPException(404,'Result is not ready')
    return json.loads(path.read_text(encoding='utf-8'))


@router.get('/{job_id}/frames/{index}')
def frame(job_id:str,index:int):
    if index not in range(3):raise HTTPException(404,'Unknown frame')
    path=folder_for(job_id)/f'{index}.png'
    if not path.exists():raise HTTPException(404,'Unknown frame')
    return FileResponse(path,media_type='image/png')
