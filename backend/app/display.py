"""Display encoding keeps missing measurements explicit and leaves science arrays intact."""
import numpy as np


def grayscale_rgb(data, valid, low, high, show_mask=False):
    if not np.isfinite([low,high]).all() or high<=low:
        raise ValueError('Display range must be finite and increasing')
    usable=np.asarray(valid,dtype=bool)&np.isfinite(data)
    stretch=np.arcsinh(10*np.clip((np.where(usable,data,low)-low)/(high-low),0,1))/np.arcsinh(10)
    pixels=np.uint8(stretch*255)
    rgb=np.repeat(pixels[...,None],3,axis=-1)
    # Neutral checkerboard means "no measurement", not a filled or inferred intensity.
    yy,xx=np.indices(data.shape)
    neutral=np.uint8(18+8*((xx+yy)%2))
    rgb[~usable]=np.repeat(neutral[...,None],3,axis=-1)[~usable]
    if show_mask:
        rgb[~usable]=[255,166,64]
    return rgb
