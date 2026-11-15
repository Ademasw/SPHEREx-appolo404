from types import SimpleNamespace
from fastapi.testclient import TestClient
from app.main import app
from app import spectrum_generation as module


def test_progressive_spectrum_converts_units_and_limits_scheduling(monkeypatch, tmp_path):
    manifest={'query':{'key':'test'},'grid':{'size_px':30},'frames':[{'visit':None},{'visit':0}]}
    requested=[]
    pipeline=SimpleNamespace(DETECTORS=('D1','D2','D3','D4','D5','D6'),
        load=lambda ra,dec,det,*args:manifest if det=='D1' else None,
        product_dir=lambda *args:tmp_path)
    jobs=SimpleNamespace(_stale=lambda m:False,
        request=lambda ra,dec,det,*args,**kwargs:requested.append((det,kwargs)) or {'status':'running'})
    def aperture(folder,m,x,y,visit,**kwargs):
        assert x==y==14.5 and kwargs['inner']==4 and kwargs['outer']==7
        return {'points':[{'flux':.002,'uncertainty':.0001,'wavelength_um':.8,
                           'time_utc':'2025-01-01T00:00:00','obs_id':str(visit)}]}
    monkeypatch.setattr(module,'aperture_spectrum',aperture)
    result=module.generate({'ra_deg':10,'dec_deg':0},.05,'none',True,False,jobs,pipeline)
    assert result['status']=='running' and result['detectors_done']==['D1']
    assert [det for det,_ in requested]==['D2','D3']
    assert all(kwargs['target'] is None and kwargs['clean'] for _,kwargs in requested)
    assert len(result['points'])==2  # unstacked exposure group is retained
    assert result['points'][0]['flux_ujy']==2000
    assert result['points'][0]['err_ujy']==100
    assert result['points'][0]['epoch']==0


def test_spectrum_terminal_errors_do_not_claim_six_successes(monkeypatch):
    pipeline=SimpleNamespace(DETECTORS=('D1','D2'),load=lambda *args:None)
    jobs=SimpleNamespace(request=lambda *args,**kwargs:{'status':'error','error':'No coverage'})
    result=module.generate({'ra_deg':10,'dec_deg':0},.05,'model',False,True,jobs,pipeline)
    assert result['status']=='done' and result['detectors_done']==[]
    assert result['errors']=={'D1':'No coverage','D2':'No coverage'}
    assert result['points']==[]


def test_spectrum_api_validates_input_and_reports_progress(monkeypatch):
    client=TestClient(app)
    assert client.get('/api/spectrum?ra=10&dec=0&fov=1').status_code==400
    assert client.get('/api/spectrum?ra=10&dec=0&bg=invalid').status_code==400
    monkeypatch.setattr(module,'generate',lambda *args:{'status':'running','points':[]})
    response=client.get('/api/spectrum?ra=0&dec=0&clean=true')
    assert response.status_code==202
