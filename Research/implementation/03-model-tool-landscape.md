# Model And Tool Landscape

## Purpose
List current practical model and tool categories aligned with this project, without implying that any single model solves the whole problem.

## Core Claim
The correct stack is not one model. It is a pipeline of capture, reconstruction, registration, segmentation, semantic enrichment, change detection, forecasting, and uncertainty-aware rendering.

## Agent Takeaways
- Use classical photogrammetry and survey tools when metric accuracy matters.
- Use foundation models to accelerate reconstruction, depth, segmentation, labeling, and search.
- Use generative models only after state estimation and uncertainty are explicit.
- Prefer primary project/docs links when updating this landscape.

## Paper Grounding
- Section 5.9, report p. 87: AI/ML can automate data mining, Scan-to-BIM, classification, semantic enrichment, prediction, and near-real-time responses.
- Section 4.4, report pp. 79-82: interoperability and metadata/paradata are critical for long-term reuse.
- Section 3.12.1, report p. 71: uncertainty must be evaluated and expressed.

## Reconstruction And Geometry
- [COLMAP](https://colmap.github.io/): general-purpose Structure-from-Motion and Multi-View Stereo pipeline.
- [OpenMVS](https://github.com/cdcseacave/openMVS): open Multi-View Stereo reconstruction library.
- [RealityCapture](https://www.capturingreality.com/realitycapture): commercial photogrammetry from images and/or laser scans.
- [DUSt3R](https://github.com/naver/dust3r): dense unconstrained stereo 3D reconstruction.
- [MASt3R](https://github.com/naver/mast3r): 3D-grounded image matching and stereo reconstruction.
- [VGGT](https://github.com/facebookresearch/vggt): feed-forward model for camera parameters, depth maps, point maps, and 3D tracks.

## Neural And Radiance Representations
- [Nerfstudio](https://docs.nerf.studio/): framework for NeRF and related neural rendering workflows.
- [Splatfacto](https://docs.nerf.studio/nerfology/methods/splat.html): Nerfstudio Gaussian Splatting implementation.
- Gaussian splats: efficient visual representation for novel view rendering, useful for inspection and communication, but not a substitute for the raw evidence archive.
- [D-NeRF](https://arxiv.org/abs/2011.13961), [Nerfies](https://openaccess.thecvf.com/content/ICCV2021/html/Park_Nerfies_Deformable_Neural_Radiance_Fields_ICCV_2021_paper.html), and [K-Planes](https://arxiv.org/abs/2301.10241): dynamic radiance-field methods for changing scenes.
- [4D Gaussian Splatting](https://arxiv.org/abs/2310.08528) and [Dynamic 3D Gaussians](https://arxiv.org/abs/2308.09713): dynamic scene representations for interactive temporal playback.
- [PAC-NeRF](https://arxiv.org/abs/2303.05512): physics-augmented radiance-field method; conceptually useful for predicting state first and rendering second.

## Segmentation, Semantics, And Depth
- [SAM 2](https://about.fb.com/news/2024/07/our-new-ai-model-can-segment-video/): promptable image and video segmentation from Meta.
- [Grounding DINO](https://github.com/IDEA-Research/GroundingDINO): open-set object detection from image-text prompts.
- [DINOv2](https://github.com/facebookresearch/dinov2): self-supervised visual features useful for retrieval, clustering, and downstream vision tasks.
- [Depth Anything V2](https://github.com/DepthAnything/Depth-Anything-V2): monocular depth foundation model.
- [OpenScene](https://github.com/pengsongyou/openscene): open-vocabulary 3D scene understanding.
- [OpenMask3D](https://openmask3d.github.io/): open-vocabulary 3D instance segmentation.
- [Pointcept](https://github.com/Pointcept/Pointcept): point-cloud perception research codebase.
- [SAGA](https://jumpat.github.io/SAGA/): promptable segmentation for 3D Gaussian splats.

## Point-Cloud, Mesh, And Geospatial Processing
- [CloudCompare M3C2](https://cloudcompare.org/doc/wiki/index.php/PluginM3C2): robust signed distances between point clouds; relevant for change detection.
- [Open3D](https://www.open3d.org/): 3D data processing, registration, geometry, and visualization library.
- [PDAL](https://pdal.io/): point-cloud data processing, especially LiDAR pipelines.
- [MeshLab](https://www.meshlab.net/): mesh cleaning, inspection, conversion, and processing.
- [QGIS](https://www.qgis.org/documentation/): geospatial context and site-scale mapping.

## Historical GIS And 4D Scaffolding
- [World Historical Gazetteer](https://www.whgazetteer.org/) and [WHG docs](https://docs.whgazetteer.org/): linked historical place data and reconciliation.
- [Linked Places Format](https://github.com/LinkedPasts/linked-places-format): GeoJSON-LD pattern for place attestations, citations, and temporal scoping.
- [Pleiades](https://pleiades.stoa.org/places) and [PeriodO](https://perio.do/technical-overview/): place and period authority precedents.
- [OpenHistoricalMap](https://www.openhistoricalmap.org/): time-enabled map data with start/end-date conventions.
- [Allmaps](https://allmaps.org/): IIIF georeferencing annotations for historical maps.
- [MapKurator](https://arxiv.org/abs/2306.17059): historical-map text extraction/georeferencing lead.
- [CityGML](https://www.ogc.org/standards/citygml), [CityJSON](https://www.cityjson.org/), and [CityJSON versioning](https://www.cityjson.org/experimental/versioning/): semantic city-object and versioning scaffolds.

## Data Spaces, Repositories, And Packaging
- [EUreka3D Data Hub](https://eureka3d.eu/eureka3d-data-hub/): upload, storage, metadata, paradata links, viewer derivatives, and Europeana publication pattern.
- [3DBigDataSpace](https://3dbigdataspace.eu/): large-scale 3D aggregation, AI enrichment, raw/model/viewer-derivative handling, and 4D tooling direction.
- [OpenHeritage3D](https://openheritage3d.org/data): reusable 3D heritage survey archive.
- [E-ARK 3D Heritage Model specification](https://3dhm.openpreservation.org/): long-term preservation package pattern for 3D heritage model data.
- [RO-Crate](https://www.researchobject.org/ro-crate/specification/1.0/index.html): practical research-object package for files, metadata, workflows, software, and provenance.

## Prediction Layer
There is no off-the-shelf model that turns arbitrary RAW, LiDAR, thermal, and spectral archives into validated future images. The project needs a custom loop:

```text
registered state series -> change measurements -> transition assumptions/model
-> future-state ensemble -> rendered forecast -> next-scan validation
```

Scenario engines and world models should be researched as conditioning frameworks, not as prompt-driven visual generators. Useful adjacent references include [Waymax](https://waymo.com/research/waymax/), [nuPlan](https://arxiv.org/abs/2106.11810), and [ASAM OpenSCENARIO](https://report.asam.net/asam-openscenario).

## Evidence / Inference / Visualization
Model outputs are inference unless they are raw sensor evidence. A SAM mask, OpenMask3D segment, depth map, Gaussian splat, or future render must be stored with method, version, inputs, and uncertainty/limitations.

## Future-State Imaging Implication
Use these tools to make the world measurable, queryable, and comparable first. The generative layer should render from constrained state, not invent from prompt alone.
