import io

import numpy as np
from astropy.io import fits

from app.fastfits import prefix_length


def make_cutout_bytes():
    hdus = fits.HDUList([fits.PrimaryHDU()])
    for name in ("IMAGE", "FLAGS", "VARIANCE", "ZODI"):
        hdus.append(fits.ImageHDU(np.ones((58, 58), dtype=np.float32), name=name))
    hdus.append(fits.BinTableHDU.from_columns([fits.Column("EPSF", "1089D", array=np.zeros((50, 1089)))], name="EPSF"))
    buffer = io.BytesIO()
    hdus.writeto(buffer)
    return buffer.getvalue()


def test_prefix_stops_after_zodi_and_is_valid_fits():
    data = make_cutout_bytes()
    length = prefix_length(data)
    assert length is not None and length < len(data)
    with fits.open(io.BytesIO(data[:length])) as prefix:
        assert [h.name for h in prefix] == ["PRIMARY", "IMAGE", "FLAGS", "VARIANCE", "ZODI"]
        assert prefix["ZODI"].data.shape == (58, 58)


def test_prefix_incomplete_returns_none():
    data = make_cutout_bytes()
    length = prefix_length(data)
    assert prefix_length(data[:length - 100]) is None
    assert prefix_length(data[:1000]) is None
