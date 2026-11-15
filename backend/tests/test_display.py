import numpy as np
from app.display import grayscale_rgb


def test_mask_is_neutral_by_default_and_amber_only_in_overlay():
    data=np.array([[1.,np.nan],[3.,4.]])
    original=data.copy()
    valid=np.isfinite(data)
    normal=grayscale_rgb(data,valid,0,5)
    mask=grayscale_rgb(data,valid,0,5,True)
    assert normal[0,1,0]==normal[0,1,1]==normal[0,1,2]
    assert mask[0,1].tolist()==[255,166,64]
    np.testing.assert_array_equal(normal[valid],mask[valid])
    np.testing.assert_array_equal(data,original)
