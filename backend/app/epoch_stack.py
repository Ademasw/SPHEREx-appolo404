"""Combine real, aligned observations; invalid samples never receive weight."""
import numpy as np


def combine_epoch(images, variances, wavelengths, reference_wave, tolerance):
    image=np.stack(images)
    variance=np.stack(variances)
    wave=np.stack(wavelengths)
    usable=(np.isfinite(image)&np.isfinite(variance)&(variance>0)&np.isfinite(wave)
            &(np.abs(wave-reference_wave)<=tolerance))
    weight=np.divide(1.,variance,out=np.zeros_like(variance,dtype=float),where=usable)
    total=weight.sum(axis=0)
    mean=np.divide((np.where(usable,image,0)*weight).sum(axis=0),total,
                   out=np.full(total.shape,np.nan),where=total>0)
    return mean,usable.sum(axis=0)
