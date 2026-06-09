# Derived Data, Formats, And Standards

## Purpose
Summarize the report's treatment of derived data, formats, and interoperability, with emphasis on why future AI/digital-twin work needs more than final meshes.

## Core Claim
Raw capture is not the final deliverable. 3D digitisation produces a chain of derived data: point clouds, meshes, imagery, CAD/BIM products, orthographic outputs, metadata, paradata, archive packages, and visualizations. Interoperability determines whether future systems can reuse the evidence.

## Agent Takeaways
- Preserve raw data and derived data separately.
- Prefer open, documented formats where practical.
- Avoid treating exported meshes as complete records.
- Store provenance and conversion history beside every artifact.

## Paper Grounding
- Section 2.10, report p. 22: data quality and project complexity are linked; quality parameters apply to geometry and additional layers such as RGB, infrared, and other coatings.
- Section 4, report pp. 72-74: standards organize project goals, deliverables, documentation, data formats, archiving, and interoperability.
- Section 4.2, report pp. 74-77: formats include LAS/LAZ, E57, OBJ, STL, 3MF, PLY, X3D, JPG, TIFF, GeoTIFF, RAW, and DNG.
- Section 4.4, report pp. 79-82: format obsolescence, interoperability gaps, and preservation metadata are major risks.

## Important Formats
| Format | Use |
| --- | --- |
| E57 | open format for point clouds, images, metadata from 3D imaging systems. |
| LAS/LAZ | LiDAR point-cloud exchange/archive, especially aerial/geospatial workflows. |
| PLY | scanner-oriented geometry with optional color, normals, confidence values. |
| OBJ | simple exchange geometry with vertices, faces, UVs, normals. |
| STL | 3D printing geometry; lacks color, texture, and rich attributes. |
| 3MF | 3D printing package with mesh, materials, colors, and extensibility. |
| TIFF/GeoTIFF | high-quality raster and georeferenced imagery. |
| DNG/TIFF | archival routes for camera RAW workflows. |
| glTF/GLB | web/XR delivery of 3D assets; useful as a derivative, not as the only archive. |
| CityGML/CityJSON | semantic city-model exchange; relevant when site scans become urban 4D systems. |
| 3D Tiles | streamed geospatial 3D delivery for city/site-scale viewers. |

## Future-State Imaging Implication
A predictive pipeline needs raw evidence, not only display derivatives. It needs:

- original photos/scans/spectra;
- calibration and control data;
- registered geometry;
- semantic labels;
- uncertainty fields;
- temporal version history;
- processing provenance.

## Data-Space Expansion
The Time Machine and Europeana-facing materials make the format problem larger. The world is not merely being saved as files. It is being aggregated into cultural-heritage data spaces, repository APIs, semantic records, and web viewers. The deeper issue is interoperability across evidence types:

- raw sensor evidence: RAW/DNG/TIFF imagery, LiDAR, E57, LAS/LAZ, spectra, thermal files;
- reconstruction intermediates: camera calibration, COLMAP/OpenMVS/RealityCapture outputs, depth maps, dense clouds;
- display derivatives: glTF/GLB, Draco-compressed assets, web textures, XR-ready scenes, Gaussian splat packages;
- semantic records: Europeana/EDM, LIDO, CARARE, CIDOC CRM, CRMdig, IIIF annotations, PROV-O, RO-Crate;
- urban/geospatial context: GeoTIFF, GIS layers, CityGML, CityJSON, 3D Tiles, OGC-style web services.

Europeana-style modeling is especially useful because it avoids collapsing the physical thing into the digital file. The EDM pattern distinguishes the cultural object, its digital web resources, and the aggregation record that packages metadata and access. For future-state imaging, a similar separation is required:

```text
physical entity
  != raw capture artifact
  != derived model
  != semantic annotation
  != forecast visualization
```

## Repositories And Benchmarks
Open repositories are not just download sources. They are examples of how future agents should package reusable 3D evidence.

- [OpenHeritage3D](https://openheritage3d.org/data) `primary/repository`: open 3D survey data; useful because the accompanying [archival framework paper](https://isprs-archives.copernicus.org/articles/XLVIII-2-2024/241/2024/) explicitly foregrounds metadata, paradata, reuse, reproducibility, and data quality.
- [CULTURE3D](https://memories.ai/research/CULTURE3D) and its [GitHub repository](https://github.com/openinterx/culture3d) `research/project`: high-resolution cultural landmark imagery, point clouds, COLMAP/RealityCapture derivatives, TLS ground truth, and Gaussian-splat benchmarks. Treat as a benchmark and method signal, not a preservation standard.
- [ISPRS Benchmarks](https://www.isprs.org/resources/datasets/benchmarks/) `primary/benchmark`: important for the validation habit; useful datasets usually include ground truth, task definitions, and scoring expectations.
- [E-ARK CITS 3D Heritage Model](https://3dhm.openpreservation.org/) `primary/spec`: preservation packaging pattern for 3D heritage model data. It reinforces the rule that multiple representations and documentation/paradata reduce format-obsolescence risk.

## Data-Space Projects
- [EUreka3D Data Hub](https://eureka3d.eu/eureka3d-data-hub/) `primary/project`: storage, management, and publication support for high-quality 3D cultural heritage, including sharing to Europeana and the common European data space for cultural heritage.
- [3DBigDataSpace](https://www.dataspace-culturalheritage.eu/en/projects/3dbigdataspace) `primary/project`: current Time Machine-adjacent infrastructure for large-scale 3D model aggregation, long-term storage, viewer derivatives, AI enrichment, and 3D/4D access.
- [Europeana 3D/XR programming](https://pro.europeana.eu/event/reimagining-cultural-heritage-in-3d-and-xr) `primary/project`: evidence that 3D and XR are becoming data-space workflows rather than isolated exhibits.
- [OGC 3D Tiles](https://www.ogc.org/standards/3DTiles) `primary/standard`: relevant when registered site models need streamed, tiled, geospatial visualization.

## Evidence / Inference / Visualization
Formats should not blur epistemic status. A `PLY` point cloud with confidence fields is not the same thing as a hand-cleaned mesh. A Gaussian splat is an excellent visual representation, but it should not become the only archive record.

## Practical Rule
Archive for future interpretation, not only present viewing. A viewer derivative can be beautiful and useful, but the durable record is the package of raw evidence, derived states, semantic annotations, metadata, paradata, provenance, and uncertainty.
