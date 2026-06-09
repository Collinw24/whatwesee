# Data Modalities

## Purpose
Define what kinds of data this project should expect and how each modality contributes to a state estimate.

## Core Claim
The goal is not to collect every possible signal. The goal is to collect enough calibrated, comparable evidence to estimate physical state, track change, and constrain future-state rendering.

## Agent Takeaways
- Treat every modality as partial evidence.
- Store raw data separately from working derivatives.
- Record calibration, coordinate frame, capture conditions, and known failure modes.
- Link all modalities through registration and metadata/paradata.

## Paper Grounding
- Section 2.4-2.6, report pp. 8-18: capture methods include manual measurement, GNSS, total station, LiDAR, photogrammetry, X-ray, infrared, multisensory and multispectral techniques.
- Section 2.8-2.9, report pp. 19-21: environment, distance, incidence angle, reflectivity, transmittance, and surface condition affect capture quality.
- Section 3.12, report pp. 67-70: quality includes geometry, material, structural health, image, scale, and spectral parameters.

## Modality Inventory
| Modality | Evidence captured | Use in state estimate |
| --- | --- | --- |
| RAW photography | high-bit-depth visible appearance and EXIF | texture, photogrammetry, color calibration, archival evidence. |
| JPEG/TIFF working images | normalized reconstruction input | COLMAP, masking, segmentation, splatting. |
| LiDAR/TLS/phone LiDAR | metric or approximate depth/geometry | scale, geometry, registration, rough spatial baseline. |
| Photogrammetry | camera poses, sparse/dense points, mesh, texture | high-detail visual geometry and appearance. |
| Thermal/IR | emitted radiation and emissivity-dependent signals | moisture, voids, heat anomalies, hidden condition. |
| Multispectral/spectral | wavelength-dependent response | material/pigment/coating classification. |
| RTI/photometric stereo | reflectance and microgeometry under varied light | surface microstructure, relighting, condition. |
| Environmental sensors | humidity, temperature, light/UV, vibration, moisture | drivers for transition dynamics. |
| Manual measurements | scale bars, calipers, notes | validation, scale, control values. |
| Historical maps/plans | documented prior geometry and layout | retrospective state constraints and source-documented hypotheses. |
| Gazetteers/place IDs | place names, temporal validity, linked identifiers | stable identity across changing names, boundaries, and records. |
| Archival photographs/video | prior visible states and context | historical texture/geometry hints, repair history, public memory. |
| IIIF/Web annotations | source regions and georeference links | evidence overlays and cited map/photo alignment. |

## Required Modality Metadata
Each modality should carry the fields needed to make it comparable later:

- coordinate frame or registration target;
- capture timestamp and timezone;
- device, lens/sensor, calibration, and firmware/software version;
- operator or agent;
- environmental conditions;
- scale/control references;
- known failure modes;
- processing steps and parameters;
- uncertainty or precision fields where available.

For material-state sensors, add:

- emissivity assumptions for thermal work;
- illumination and white/color calibration for spectral/RGB work;
- moisture/weather history for exterior surfaces;
- sensor warmup, distance, angle, and integration settings;
- mask/ROI definitions and review status.

## Evidence / Inference / Visualization
- Evidence: RAW files, LiDAR scans, thermal frames, spectral bands, sensor logs.
- Inference: depth maps, registered clouds, masks, material labels, anomaly maps.
- Visualization: splats, meshes, orthophotos, overlays, forecasts.

## Future-State Imaging Implication
Future-state rendering should be conditioned on the modalities that actually explain change. A weathering forecast needs material and exposure evidence. A crack forecast needs geometry and structural context. A moisture forecast needs thermal/IR, humidity, and environmental history.

## Minimal Starter Dataset
For a first experiment:

- 100-250 RAW+JPEG photos;
- scale bars or known-size markers;
- one rough LiDAR pass if available;
- environmental note: date, time, weather/room conditions, lighting, humidity if available;
- region-of-interest labels;
- repeat capture after a meaningful interval.

## Link To Existing Pipeline
The existing [../../photogrammetry/README.md](../../photogrammetry/README.md) already defines local ingest, QC, Hetzner staging, Vast.ai jobs, COLMAP/OpenMVS, and Nerfstudio Splatfacto outputs. This research system should treat that pipeline as the first practical capture-to-representation layer.

## Data-Space Package Target
For research artifacts intended to survive beyond one experiment, mirror the EUreka3D/Europeana pattern:

- raw evidence preserved separately from working derivatives;
- one or more viewer derivatives such as glTF/GLB or splats;
- metadata for object, web resource, and aggregation/package;
- paradata link for capture and processing decisions;
- PID or stable local identifier;
- rights/access status;
- uncertainty and validation notes.
