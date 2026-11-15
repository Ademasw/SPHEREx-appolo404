"""Exploratory aperture photocentres; not a calibrated PSF astrometry pipeline."""
import numpy as np


def photocentre(image, variance, valid, x, y, radius=3):
    yy,xx=np.indices(image.shape)
    distance=np.hypot(xx-x,yy-y)
    good=valid & np.isfinite(image) & np.isfinite(variance) & (variance>0)
    aperture=(distance<=radius)&good
    annulus=(distance>=radius+1)&(distance<=radius+3)&good
    if aperture.sum()<8 or annulus.sum()<12:
        raise ValueError('Insufficient usable aperture/background pixels')
    if good[distance<=1.5].mean()<.8:
        raise ValueError('Core is masked')
    background=np.median(image[annulus])
    # Signed background-subtracted flux, without clipping negative noise.
    flux=np.where(aperture,image-background,0)
    total=flux.sum()
    if total<=0:
        raise ValueError('No positive integrated signal')
    cx=float((flux*xx).sum()/total);cy=float((flux*yy).sum()/total)
    if np.hypot(cx-x,cy-y)>radius/2:
        raise ValueError('Centroid outside allowed neighborhood')
    # Linearized pixel-noise contribution; background/PSF systematics excluded.
    vx=float((np.where(aperture,variance,0)*(xx-cx)**2).sum()/total**2)
    vy=float((np.where(aperture,variance,0)*(yy-cy)**2).sum()/total**2)
    return {'x':cx,'y':cy,'sigma_x_pixel':np.sqrt(vx),'sigma_y_pixel':np.sqrt(vy),
            'background':float(background),'flux_sum':float(total),'n_pixels':int(aperture.sum())}


def robust_translation(offsets):
    offsets=np.asarray(offsets,dtype=float)
    if offsets.ndim!=2 or offsets.shape[1]!=2 or not len(offsets):
        raise ValueError('Need reference offsets')
    centre=np.median(offsets,axis=0)
    residual=np.linalg.norm(offsets-centre,axis=1)
    limit=max(.3,3*1.4826*np.median(np.abs(residual-np.median(residual))))
    keep=residual<=limit
    return np.median(offsets[keep],axis=0),keep
