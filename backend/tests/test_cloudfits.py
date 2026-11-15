import json

import numpy as np
from astropy.wcs import WCS

from app.cloudfits import cloud_url, shift_header
from app.preview import make_grid


def test_cloud_url_accepts_only_the_spherex_bucket():
    good = json.dumps({"aws": {"bucket_name": "nasa-irsa-spherex", "region": "us-east-1",
                               "key": "dr1/level2/x/D3.fits"}})
    assert cloud_url(good) == "https://nasa-irsa-spherex.s3.us-east-1.amazonaws.com/dr1/level2/x/D3.fits"
    other = json.dumps({"aws": {"bucket_name": "someone-else", "region": "us-east-1", "key": "dr1/a.fits"}})
    traversal = json.dumps({"aws": {"bucket_name": "nasa-irsa-spherex", "region": "us-east-1", "key": "dr1/../a"}})
    assert cloud_url(other) is None
    assert cloud_url(traversal) is None
    assert cloud_url("") is None


def test_shifted_header_points_to_the_same_sky():
    full, _ = make_grid(130, -7, fov_deg=0.5)
    header = full.to_header()
    header["CRPIX1W"], header["CRPIX2W"] = 1.0, 1.0
    section = shift_header(header, 40, 25)
    sky_full = WCS(header).pixel_to_world(np.array([50.0]), np.array([30.0]))
    sky_section = WCS(section).pixel_to_world(np.array([10.0]), np.array([5.0]))
    assert sky_full.separation(sky_section).arcsec[0] < 1e-6
    assert section["CRPIX1W"] == -39 and section["CRPIX2W"] == -24
