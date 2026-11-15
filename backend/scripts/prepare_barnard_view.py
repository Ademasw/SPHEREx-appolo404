"""Publish inspected Barnard frames with quality warnings, never synthetic motion."""
import json
import shutil

from astropy.coordinates import SkyCoord

from app.archive import ROOT


def main():
    folder = ROOT / 'data/barnard'
    inspected = [frame for frame in json.loads((folder / 'inspection.json').read_text(encoding='utf-8'))
                 if frame['observation']['energy_bandpassname']=='SPHEREx-D1']
    if len(inspected) < 2:
        raise ValueError('Need two successfully inspected observations')
    inspected = inspected[:2]
    target = next(t for t in json.loads((ROOT/'data/catalog/audit.json').read_text(encoding='utf-8'))['targets'] if t['id']=='barnard')
    coordinates = [SkyCoord(f['predicted_position']['ra_deg'], f['predicted_position']['dec_deg'], unit='deg') for f in inspected]
    predicted_shift = float(coordinates[0].separation(coordinates[1]).arcsec)
    frames = []
    for i, frame in enumerate(inspected):
        source_index = frame.get('render_index', i)
        shutil.copyfile(folder/f'inspect-{source_index}.png',folder/f'{i}.png')
        frames.append({**frame, 'index':i, 'center_wavelength_um':frame['wavelength_um'],
                       'center_bandwidth_um':frame['bandwidth_um'],
                       'usable_grid_fraction':frame['nearby_usable_count']/frame['nearby_pixel_count'],
                       'image_url':f'/api/barnard/frames/{i}',
                       'quality_summary':f"{frame['nearby_usable_count']} of {frame['nearby_pixel_count']} nearby pixels usable"})
    manifest = {
        'target_name':"Barnard's Star field", 'detector':'D1',
        'field_note':'Bright source at the catalog-predicted location. Orange circle marks prediction, not a measured centroid.',
        'query':{'ra_deg':target['search_position']['ra_deg'],'dec_deg':target['search_position']['dec_deg'],'release':'dr1'},
        'grid':{'fov_deg':.05,'pixel_arcsec':6.2}, 'frames':frames,
        'predicted_motion_arcsec':predicted_shift,
        'mode_note':'Source-location inspection. Core pixels carry processing-error flags; these wavelengths differ. This is not a motion measurement.',
        'quality_label':'Usable near target',
        'warnings':[
            'Orange circle is proper-motion prediction from SIMBAD, not a detected centroid. Observer parallax is not applied.',
            f'Predicted displacement between these dates: {predicted_shift:.2f} arcsec; this is calculated, not measured from images.',
            'A bright source is visible around the predicted location, but core pixels have OVERFLOW/SUR_ERROR and BLOOM flags.',
            'Per-frame display stretch differs for inspection; wavelengths also differ. Do not interpret brightness changes as variability.',
            'Movement measurement requires better-quality comparable observations or a validated fit to usable source wings.'
        ]}
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False),encoding='utf-8')
    print(f"Prepared source-location view. Predicted, not measured, shift: {predicted_shift:.2f} arcsec")


if __name__=='__main__':
    main()
