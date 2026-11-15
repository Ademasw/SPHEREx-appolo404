import numpy as np
from app.epoch_stack import combine_epoch


def test_only_real_compatible_observations_fill_gaps():
    a=np.array([[1.,np.nan,np.nan]])
    b=np.array([[3.,5.,9.]])
    v=np.ones_like(a)
    wave=np.ones_like(a)*2
    other=wave.copy();other[0,2]=3
    out,count=combine_epoch([a,b],[v,v],[wave,other],wave,.01)
    np.testing.assert_allclose(out[0,:2],[2,5])
    assert np.isnan(out[0,2])
    assert count.tolist()==[[2,1,0]]
