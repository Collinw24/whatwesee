# Radiation And Material State

## Purpose
Track the report's deeper point that digitisation is not only about shape. Sensors measure interactions between matter and energy, which can reveal material condition and hidden state.

## Core Claim
Physical reality becomes measurable through interaction with electromagnetic radiation or other probes. Visible light captures appearance; infrared captures emitted energy and thermal behavior; X-ray and terahertz can reveal inaccessible structure; spectroscopy and multispectral imaging can expose material composition.

## Agent Takeaways
- Treat every modality as a partial measurement of physical state.
- Material state is essential for future-state rendering.
- Hidden failure often appears as weak thermal, spectral, moisture, or structural signals before visible geometry changes.
- Do not collapse multispectral, thermal, and geometric evidence into a single texture.

## Paper Grounding
- Section 2.4, report pp. 10-11: radiating energy is used to gather geometric and visual information; penetrating and non-penetrating systems are distinguished.
- Section 2.4, report pp. 10-11: X-ray captures inaccessible internal structures; infrared thermography detects subsurface defects and anomalies through temperature differences and emissivity.
- Section 2.6, report pp. 17-18: spectroscopy, ultrasonic microscopy, multispectral imaging, RTI, PTM, and photometric stereo provide complementary material, stratigraphic, reflectance, and geometry information.

## Modalities As State Probes
| Modality | Physical signal | Project use |
| --- | --- | --- |
| RGB/RAW | visible reflectance, color, texture | photogrammetry, texture, surface change. |
| Infrared/thermal | emitted radiation, emissivity, heat flow | moisture, voids, delamination, thermal anomalies. |
| Near/far IR, terahertz | surface/subsurface interaction | shallow hidden structure and material behavior. |
| X-ray/CT | penetrating internal structure | hidden voids, construction, internal damage. |
| Multispectral imaging | wavelength-dependent reflectance | pigment/material detection, underdrawings, coatings. |
| Spectroscopy | molecular/elemental signatures | material identification and conservation state. |
| RTI/PTM/photometric stereo | reflectance under changing light | microstructure, surface relief, relighting. |
| Ultrasonic microscopy | acoustic structural response | internal structure and defects. |

## Dataset And Method Leads
Material decay is where "future-state imaging" becomes more than geometry. Useful leads:

- [Dazu Rock Carvings hyperspectral dataset](https://www.nature.com/articles/s41597-025-06158-3) `peer-reviewed dataset`: visible and hyperspectral data for stone-relic deterioration classes such as cracks/deformation, detachment, material loss, discoloration/deposit, and biological colonization.
- [SWIR porous-stone moisture dataset](https://zenodo.org/records/17726161) `dataset`: hyperspectral cubes and moisture maps for historic stone/brick materials; useful for learning moisture-state priors.
- [Terahertz stone deterioration prediction](https://www.nature.com/articles/s40494-021-00502-7) `peer-reviewed`: non-destructive testing and machine-learning prediction for hollowing deterioration in stone relics.
- [IRT + 3D fusion review](https://www.mdpi.com/2072-4292/15/9/2422) `review`: infrared thermography fused with 3D data for built-heritage diagnosis.
- [CODEBRIM](https://arxiv.org/abs/1904.08486), [SDNET2018](https://digitalcommons.usu.edu/all_datasets/48), and [wood surface defect data](https://pmc.ncbi.nlm.nih.gov/articles/PMC9277195/) `datasets/peer-reviewed`: defect and crack priors from infrastructure/material inspection. Useful, but domain shift must be explicit.

These sources are priors and testbeds, not substitutes for local measurement. A crack classifier trained on concrete bridge images does not validate a forecast for a stone facade without calibration and review.

## Future-State Imaging Implication
The future renderer needs material constraints. A crack forecast, decay forecast, restored-state reconstruction, or thermal-anomaly projection should not be driven by geometry alone. Material class, moisture behavior, exposure, emissivity, reflectance, coating, stratigraphy, and prior interventions change the transition dynamics.

Early failure often appears first as weak signal rather than visible geometry: a recurring cool/warm thermal anomaly, a moisture band, a spectral shift, a slight displacement above level of detection, or a surface-change cluster. The forecast pipeline should preserve those weak signals with uncertainty instead of smoothing them away as noise.

## Evidence / Inference / Visualization
- Evidence: spectral bands, thermal frames, X-ray images, ultrasonic readings, raw photos.
- Inference: material labels, moisture zones, subsurface anomalies, degradation hypotheses.
- Visualization: overlays, false color maps, relit surfaces, future material-state renderings.

## Practical Rule
Every pixel can contain more than color. It can contain spectra, geometry, stratigraphy, reflectance, condition, and uncertainty.
