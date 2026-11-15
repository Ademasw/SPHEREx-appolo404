import numpy as np
from app.centroid import photocentre,robust_translation


def test_photocentre_recovers_subpixel_source_without_catalog_copy():
    y,x=np.indices((25,25));image=10+100*np.exp(-((x-12.3)**2+(y-11.7)**2)/(2*.7**2))
    fit=photocentre(image,np.ones_like(image),np.ones_like(image,dtype=bool),12,12)
    assert abs(fit['x']-12.3)<.03
    assert abs(fit['y']-11.7)<.03


def test_translation_rejects_outlier():
    shift,keep=robust_translation([[1,2],[1.05,2.05],[.95,1.95],[20,30]])
    np.testing.assert_allclose(shift,[1,2])
    assert keep.tolist()==[True,True,True,False]
