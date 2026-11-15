"""Read a small section of a SPHEREx image from NASA's public cloud copy.

IRSA mirrors every SPHEREx image in the public AWS bucket `nasa-irsa-spherex`
(plain HTTPS, no account or keys). IRSA SIA returns the location of each image
in `cloud_access`. HTTP range requests read only the four headers and the rows
of the region we need (~8 requests, ~3 MB instead of the 66 MB file). Plain
`requests` is used instead of astropy+fsspec: the latter serialised parallel
reads (2 of 48 frames in 40 s with 8 threads). The cloud is not
affected by the 503 errors of the IRSA cutout service, so the pipeline uses it
when a cutout request fails. Idea and first implementation: scripts/prepare_epsilon.py.

The section is saved with the same layout as a cutout prefix (PRIMARY, IMAGE,
FLAGS, VARIANCE, ZODI) so the rest of the pipeline treats both the same way.
"""
import io
import json

import numpy as np
import requests
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS, FITSFixedWarning
import warnings

from app.fastfits import _data_size, _header_end

warnings.simplefilter("ignore", FITSFixedWarning)

BUCKET = "nasa-irsa-spherex"
EXTENSIONS = ("IMAGE", "FLAGS", "VARIANCE", "ZODI")


def cloud_url(cloud_access):
    """HTTPS URL of the public cloud copy, or None if the entry is missing or unexpected."""
    try:
        info = json.loads(cloud_access)["aws"]
    except (TypeError, ValueError, KeyError):
        return None
    key = str(info.get("key", ""))
    if info.get("bucket_name") != BUCKET or not key.startswith(("dr1/", "qr3/")) or ".." in key:
        return None
    return f"https://{BUCKET}.s3.{info.get('region', 'us-east-1')}.amazonaws.com/{key}"


def shift_header(header, x0, y0):
    """Header of the [y0:, x0:] section: every reference pixel moves by the offset.

    Covers the celestial WCS (with SIP, whose polynomials are relative to CRPIX),
    the 'A' (parent pixel) and 'W' (wavelength table) alternate systems.
    """
    shifted = header.copy()
    for suffix in ("", "A", "W"):
        for axis, offset in ((1, x0), (2, y0)):
            key = f"CRPIX{axis}{suffix}"
            if key in shifted:
                shifted[key] = shifted[key] - offset
    return shifted


def _get_range(session, url, start, length):
    response = session.get(url, headers={"Range": f"bytes={start}-{start + length - 1}"}, timeout=(10, 60))
    response.raise_for_status()
    if response.status_code != 206:
        raise ValueError("server ignored the byte range")
    return response.content


def _header_at(session, url, offset):
    """FITS header starting at `offset` and its length in bytes."""
    buffer = b""
    while True:
        buffer += _get_range(session, url, offset + len(buffer), 2880 * 12)
        end = _header_end(buffer, 0)
        if end is not None:
            return fits.Header.fromstring(buffer[:end].decode("ascii", errors="replace")), end
        if len(buffer) > 2880 * 200:
            raise ValueError("FITS header too long")


def _physical(raw, header):
    """Apply BSCALE/BZERO like astropy; keep integers (flags) as integers."""
    scale, zero = header.get("BSCALE", 1), header.get("BZERO", 0)
    if scale == 1 and float(zero).is_integer():
        return raw.astype(np.int64) + int(zero) if raw.dtype.kind == "i" else raw.astype(np.float32) + zero
    return raw * scale + zero


def _compressed_rows(session, url, header, data_offset, y0, y1):
    """Rows y0..y1 of a tile-compressed image (FLAGS is RICE-compressed in the full files).

    Reads only the tile descriptors and heap bytes of the needed tile rows, then
    lets astropy decompress a small rebuilt table with the same compression header.
    """
    tile_rows = int(header.get("ZTILE2", 1))
    if int(header.get("ZTILE1", header["ZNAXIS1"])) != int(header["ZNAXIS1"]):
        raise ValueError("only full-width tiles are supported")
    t0, t1 = y0 // tile_rows, (y1 - 1) // tile_rows + 1
    width = int(header["NAXIS1"])  # bytes per descriptor row
    if width != 8:
        raise ValueError("unexpected tile descriptor format")
    table = np.frombuffer(_get_range(session, url, data_offset + t0 * width, (t1 - t0) * width), dtype=">i4")
    counts, offsets = table[0::2].astype(np.int64), table[1::2].astype(np.int64)
    heap_start = data_offset + int(header.get("THEAP", int(header["NAXIS1"]) * int(header["NAXIS2"])))
    low, high = int(offsets.min()), int((offsets + counts).max())
    heap = _get_range(session, url, heap_start + low, high - low)
    rebuilt = np.empty(2 * (t1 - t0), dtype=">i4")
    rebuilt[0::2], rebuilt[1::2] = counts, offsets - low
    small = header.copy()
    small["NAXIS2"] = t1 - t0
    small["ZNAXIS2"] = min(int(header["ZNAXIS2"]) - t0 * tile_rows, (t1 - t0) * tile_rows)
    small["PCOUNT"] = len(heap)
    small["THEAP"] = (t1 - t0) * width
    body = rebuilt.tobytes() + heap
    body += b"\x00" * (-len(body) % 2880)
    blob = fits.PrimaryHDU().header.tostring().encode() + small.tostring().encode() + body
    with fits.open(io.BytesIO(blob)) as hdus:
        rows = np.asarray(hdus[1].data)
    return rows[y0 - t0 * tile_rows:y1 - t0 * tile_rows]


def fetch_section(url, ra, dec, fov_deg, path, pixel_arcsec=6.2, stop=None, session=None):
    """Write the section covering a fov_deg field around (ra, dec) to `path`."""
    session = session or requests.Session()
    half = int(np.ceil(fov_deg * 3600 / pixel_arcsec * 0.75)) + 4  # covers the rotated square grid
    primary, offset = _header_at(session, url, 0)
    offset += _data_size(primary)
    headers = {}
    for name in EXTENSIONS:  # extensions follow each other in this order in SPHEREx files
        if stop is not None and stop.is_set():
            raise TimeoutError("time budget exhausted")
        header, length = _header_at(session, url, offset)
        if str(header.get("EXTNAME", "")).strip().upper() != name:
            raise ValueError(f"unexpected extension order at {name}")
        headers[name] = (header, offset + length)
        offset += length + _data_size(header)
    image_header = headers["IMAGE"][0]
    nx, ny = int(image_header["NAXIS1"]), int(image_header["NAXIS2"])
    x, y = WCS(image_header).world_to_pixel(SkyCoord(ra, dec, unit="deg"))
    x0, x1 = max(0, int(x) - half), min(nx, int(x) + half + 1)
    y0, y1 = max(0, int(y) - half), min(ny, int(y) + half + 1)
    if x1 - x0 < 4 or y1 - y0 < 4:
        raise ValueError("position falls outside this image")
    out = fits.HDUList([fits.PrimaryHDU(header=primary)])
    for name in EXTENSIONS:
        header, data_offset = headers[name]
        if stop is not None and stop.is_set():
            raise TimeoutError("time budget exhausted")
        if header.get("ZIMAGE"):
            data = _compressed_rows(session, url, header, data_offset, y0, y1)[:, x0:x1]
            plain = fits.Header()
            for card in header.cards:  # keep MSKN flag names and other metadata, drop table keywords
                if card.keyword.startswith(("MSKN", "MSKD")) or card.keyword in ("EXTNAME", "BUNIT"):
                    plain.append(card)
            out.append(fits.ImageHDU(data=data, header=plain, name=name))
            continue
        bits = int(header["BITPIX"])
        dtype = np.dtype({8: "u1", 16: ">i2", 32: ">i4", 64: ">i8", -32: ">f4", -64: ">f8"}[bits])
        row = int(header["NAXIS1"]) * dtype.itemsize
        # Rows y0..y1 are contiguous: one request, columns cut locally.
        raw = np.frombuffer(_get_range(session, url, data_offset + y0 * row, (y1 - y0) * row), dtype=dtype)
        raw = raw.reshape(y1 - y0, int(header["NAXIS1"]))[:, x0:x1]
        data = _physical(raw, header)
        clean = shift_header(header, x0, y0)
        for key in ("BSCALE", "BZERO"):
            clean.remove(key, ignore_missing=True)
        out.append(fits.ImageHDU(data=data, header=clean, name=name))
    out.writeto(path, overwrite=True)
    return (x1 - x0) * (y1 - y0)
