"""Store the per-detector wavelength lookup table (WCS-WAVE) in app/wavetables.

The table maps parent-detector pixels to wavelength and bandwidth. It is the
same for every exposure of a detector, so fast partial downloads (which stop
before WCS-WAVE) can use this stored copy. The script downloads one full
cutout per detector and release and refuses to save if releases disagree.

    python -m scripts.fetch_wavetables
"""
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import astropy.units as u
import numpy as np
import requests
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astroquery.ipac.irsa import Irsa

from app.archive import ROOT

OUT = ROOT / "app" / "wavetables"
PROBE = SkyCoord(269.4462679, 4.7682044, unit="deg")  # covered by DR1 and QR3


def table_for(urls):
    """First candidate URL that yields a table; single files can fail persistently."""
    for url in urls:
        for attempt in range(3):
            try:
                response = requests.get(url + "?center=269.4462679,4.7682044d&size=0.01", timeout=(15, 180))
                response.raise_for_status()
                with fits.open(BytesIO(response.content)) as hdus:
                    return fits.BinTableHDU(data=hdus["WCS-WAVE"].data.copy(),
                                            header=hdus["WCS-WAVE"].header.copy())
            except Exception:
                time.sleep(3 * (attempt + 1))  # IRSA often answers 503 under load
    raise RuntimeError(f"No candidate worked: {urls[0]}")


def main():
    Irsa.TIMEOUT = 300
    rows = {}
    for collection in ("spherex_dr1", "spherex_qr3"):
        for attempt in range(5):
            try:
                result = Irsa.query_sia(pos=(PROBE, 1 * u.arcsec), collection=[collection])
                break
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(10 * (attempt + 1))
        for row in result:
            rows.setdefault((str(row["energy_bandpassname"]), collection), []).append(str(row["access_url"]))
    jobs = {key: urls[::max(1, len(urls) // 6)][:6] for key, urls in rows.items()}
    with ThreadPoolExecutor(3) as pool:
        tables = dict(zip(jobs, pool.map(table_for, jobs.values())))
    OUT.mkdir(parents=True, exist_ok=True)
    for detector in range(1, 7):
        band = f"SPHEREx-D{detector}"
        found = [tables[key] for key in tables if key[0] == band]
        if not found:
            raise SystemExit(f"No table for {band}")
        for other in found[1:]:
            if not np.array_equal(found[0].data["VALUES"], other.data["VALUES"]):
                raise SystemExit(f"{band}: tables differ between releases; per-exposure tables required")
        found[0].writeto(OUT / f"D{detector}.fits", overwrite=True)
        print(f"D{detector}: saved, compared across {len(found)} release(s)")


if __name__ == "__main__":
    main()
