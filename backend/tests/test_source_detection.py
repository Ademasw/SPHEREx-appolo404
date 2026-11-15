import numpy as np
from app.source_detection import inspect_source


def test_candidate_is_measured_from_data_not_copied_from_prediction():
    image = np.zeros((25,25))
    image[13,11] = 20
    result = inspect_source(image,np.ones_like(image),np.ones_like(image,dtype=bool),12,12)
    assert result['status']=='signal_candidate'
    assert result['peak_pixel']==[11,13]
    assert result['peak_pixel_snr']==20


def test_flagged_core_prevents_reliable_detection_claim():
    image = np.zeros((25,25))
    image[13,11] = 20
    valid = np.ones_like(image,dtype=bool)
    valid[11:14,11:14] = False
    assert inspect_source(image,np.ones_like(image),valid,12,12)['status']=='not_reliable'


def test_flat_background_does_not_become_detection():
    image = np.ones((25,25))*10
    assert inspect_source(image,np.ones_like(image),np.ones_like(image,dtype=bool),12,12)['status']=='not_reliable'
