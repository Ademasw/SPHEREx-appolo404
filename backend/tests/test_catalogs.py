from app import catalogs
from app.preview import make_grid


def test_catalog_markers_use_wcs_and_keep_missing_motion_unknown(monkeypatch):
    grid, size=make_grid(10, -20, .05)
    manifest={'query':{'ra_deg':10,'dec_deg':-20,'fov_deg':.05},
              'grid':{'header':dict(grid.to_header()),'size_px':size},
              'frames':[{'index':0,'time_utc':'2025-01-01T00:00:00'}]}
    monkeypatch.setattr(catalogs,'_query',lambda *args:[{'source_id':'123','ra':'10','dec':'-20','ref_epoch':'2016','pmra':'','pmdec':''}])
    result=catalogs.overlay(manifest,0,'gaia')
    source=result['sources'][0]
    assert source['pmra_mas_yr'] is None and not source['proper_motion_applied']
    assert abs(source['grid_x'] - (size-1)/2) < 1e-6
    assert abs(source['grid_y'] - (size-1)/2) < 1e-6


def test_high_proper_motion_is_propagated_to_exposure_epoch(monkeypatch):
    grid,size=make_grid(10,0,.05)
    manifest={'query':{'ra_deg':10,'dec_deg':0,'fov_deg':.05},'grid':{'header':dict(grid.to_header()),'size_px':size},'frames':[{'index':0,'time_utc':'2026-01-01T00:00:00'}]}
    monkeypatch.setattr(catalogs,'_query',lambda *args:[{'source_id':'123','ra':'10','dec':'0','ref_epoch':'2016','pmra':'1000','pmdec':'0'}])
    source=catalogs.overlay(manifest,0,'gaia')['sources'][0]
    assert source['proper_motion_applied']
    assert source['ra_deg'] > 10 and source['grid_x'] < (size-1)/2
