"""Fast partial download of SPHEREx cutouts.

The IRSA cutout service streams a multi-extension FITS file in this order:
PRIMARY, IMAGE, FLAGS, VARIANCE, ZODI, EPSF, WCS-WAVE. For a 0.1 degree
cutout the four image extensions take about 120 KB, while the EPSF table
(a PSF model we do not use) takes about 3.9 MB, 96% of the file.

`fetch_prefix` reads the stream only until the ZODI extension is complete and
then closes the connection. The saved prefix is itself a valid FITS file with
five HDUs. The WCS-WAVE table, needed for wavelengths, is identical for all
exposures of a detector, so it is stored once per detector (see wavetables).
"""
import random
import time

import numpy as np
import requests
from astropy.io import fits

WANTED = ("IMAGE", "FLAGS", "VARIANCE", "ZODI")
BLOCK = 2880
TRANSIENT = (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError)


def _header_end(buffer, start):
    """Offset just past the header block that starts at `start`, or None if incomplete."""
    position = start
    while position + BLOCK <= len(buffer):
        block = buffer[position:position + BLOCK]
        position += BLOCK
        for card in range(0, BLOCK, 80):
            if block[card:card + 8] == b"END     ":
                return position
    return None


def _data_size(header):
    bits = abs(int(header.get("BITPIX", 8)))
    naxis = int(header.get("NAXIS", 0))
    if naxis == 0:
        return 0
    count = int(np.prod([int(header[f"NAXIS{i}"]) for i in range(1, naxis + 1)]))
    count = int(header.get("GCOUNT", 1)) * (int(header.get("PCOUNT", 0)) + count)
    size = bits // 8 * count
    return -(-size // BLOCK) * BLOCK  # padded to whole blocks


def prefix_length(buffer, wanted=WANTED):
    """Bytes needed to hold the primary HDU and all `wanted` extensions, or None if not yet."""
    position, names = 0, set()
    while True:
        end = _header_end(buffer, position)
        if end is None:
            return None
        header = fits.Header.fromstring(buffer[position:end].decode("ascii", errors="replace"))
        position = end + _data_size(header)
        if position > len(buffer):
            return None
        names.add(str(header.get("EXTNAME", "")).strip().upper())
        if all(name in names for name in wanted):
            return position


def fetch_prefix(url, path, attempts=6, timeout=(15, 60), session=None, stop=None):
    """Download only the needed leading part of a cutout to `path`. Returns bytes read.

    IRSA answers 503 to a large share of requests when busy; failures are
    random, so short jittered retries work. `stop` (threading.Event) aborts.
    """
    getter = session or requests
    last_error = None
    for attempt in range(attempts):
        if stop is not None and stop.is_set():
            raise TimeoutError("time budget exhausted")
        try:
            with getter.get(url, stream=True, timeout=timeout) as response:
                if response.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"{response.status_code} from IRSA", response=response)
                response.raise_for_status()
                buffer = bytearray()
                for chunk in response.iter_content(32768):
                    buffer += chunk
                    if len(buffer) >= BLOCK * 4:
                        length = prefix_length(bytes(buffer))
                        if length is not None:
                            path.write_bytes(bytes(buffer[:length]))
                            return len(buffer)
                    if len(buffer) > 64 * 1024 * 1024:
                        raise ValueError("Cutout stream too large")
                length = prefix_length(bytes(buffer))
                if length is None:
                    raise ValueError("Cutout ended before the image extensions were complete")
                path.write_bytes(bytes(buffer[:length]))
                return len(buffer)
        except (requests.HTTPError, *TRANSIENT) as error:
            last_error = error
            status = getattr(getattr(error, "response", None), "status_code", None)
            if status is not None and status < 500 and status != 429:
                raise
            pause = random.uniform(0.4, 1.2) * (attempt + 1)
            if stop is not None and stop.wait(pause):
                raise TimeoutError("time budget exhausted")
            if stop is None:
                time.sleep(pause)
    raise last_error
