# Research System For Future-State Imaging

## Purpose
This directory turns the VIGIE 2020/654 report, `KK0521128ENN_yK2T3mg7kjhSifoxSuRP8SJw48_86092.pdf`, into an agent-readable research system. It is both a faithful paper digest and a conceptual bridge toward future-state rendering from temporally grounded digital twins.

This pass also folds in the local Time Machine corpus under `timemachine/text/`: 44 extracted PDFs/texts on Big Data of the Past, 4D information systems, local Time Machines, Europeana/EDM, 3DBigDataSpace, FAIR 3D, historical GIS, paradata, HBIM, and virtual museums. VIGIE remains the measurement-quality anchor; the Time Machine material expands the system from single-object digitisation toward 4D evidence infrastructure.

## Core Claim
A scan is not just a scan anymore. Once capture becomes multi-sensor, calibrated, semantically annotated, repeated over time, and linked to AI/ML systems, it becomes a state estimate of a physical system. Future images generated from that state are rendered forecasts: visualizations of modeled probability distributions constrained by measured reality, not measured records of later events.

## Agent Takeaways
- Treat the PDF as the canonical source for digitisation quality, uncertainty, metadata, paradata, standards, and digital-twin foundations.
- Treat the Time Machine corpus as an adjacent evidence layer for 4D information systems, historical data graphs, local Time Machines, 3D data spaces, and retrospective reconstruction.
- Keep evidence, inference, and visualization separate in every downstream design.
- Build toward a semantic 3D time series before attempting prediction.
- Never present future-state images as proof. Present them as uncertainty-bearing forecasts that must be validated against later captures.

## Paper Grounding
- Section 2.1, report pp. 4-5: 3D digitisation supports conservation, structural assessment, education, creative industry, repositories, and public access.
- Section 3.12.1, report p. 71: uncertainty is central to digitisation quality.
- Section 5.6, report p. 86: digital twins connect virtual replicas to physical behavior, monitoring, and maintenance.
- Section 5.9, report p. 87: AI/ML can support classification, enrichment, prediction, and monitoring.

## Evidence / Inference / Visualization
- **Evidence**: raw sensor data and capture records.
- **Inference**: reconstructed geometry, labels, condition assessments, change maps, and predictions.
- **Visualization**: meshes, splats, rendered forecasts, diagrams, and presentation views.

## Reading Order
1. Start with [paper/00-paper-map.md](paper/00-paper-map.md) for report structure and section anchors.
2. Read [paper/01-central-thesis.md](paper/01-central-thesis.md) for the project interpretation.
3. Read [paper/08-derived-data-formats-standards.md](paper/08-derived-data-formats-standards.md) and [paper/09-metadata-paradata.md](paper/09-metadata-paradata.md) early, because data-space and provenance discipline now shape the whole project.
4. Read the remaining paper notes from quality through AI/ML: [paper/02-quality-and-purpose.md](paper/02-quality-and-purpose.md) through [paper/11-ai-ml-and-future-tech.md](paper/11-ai-ml-and-future-tech.md).
5. Read the theory files from [theory/01-scan-as-state-estimate.md](theory/01-scan-as-state-estimate.md) through [theory/07-validation-loop.md](theory/07-validation-loop.md).
6. Use [implementation/04-agent-operating-guide.md](implementation/04-agent-operating-guide.md), [implementation/05-experiment-roadmap.md](implementation/05-experiment-roadmap.md), and [implementation/06-basement-s0-alignment.md](implementation/06-basement-s0-alignment.md) when planning actual work.

## Expanded Corpus Scope
The corpus now has three layers:

- **Paper-grounded measurement layer**: VIGIE 2020/654 establishes capture quality, fit-for-purpose requirements, accuracy, precision, resolution, uncertainty, metadata, paradata, standards, and digital-twin foundations.
- **4D evidence-infrastructure layer**: Time Machine, Big Data of the Past, local Time Machines, historical GIS, temporal gazetteers, Europeana/EDM, EUreka3D, 3DBigDataSpace, and FAIR 3D show how digitised evidence becomes a spatial-temporal knowledge system.
- **Future-state imaging layer**: point-cloud change detection, M3C2-style validation, material decay sensing, dynamic radiance fields, 4D Gaussian splats, world models, scenario engines, and uncertainty visualization become downstream methods only after measured reality and provenance are in place.

## Research Loop Protocol
When extending this corpus, use a one-topic loop:

1. Select one topic from the queue in [paper/00-paper-map.md](paper/00-paper-map.md).
2. Research canonical sources, fringe/adjacent leads, technical methods, and counterweights separately.
3. Prefer primary sources: standards, project docs, peer-reviewed papers, datasets, GitHub repos, and institutional pages.
4. Rate sources as `primary`, `credible secondary`, or `exploratory`.
5. Merge findings into existing files only when they clarify measured state, metadata/paradata, uncertainty, validation, or rendered forecasts.
6. Preserve the central epistemic rule: generated future images are visualizations of modeled probability distributions, not evidence of the future.

## File Map
### Paper Digest
- [paper/00-paper-map.md](paper/00-paper-map.md): report metadata, table of contents, and source anchors.
- [paper/01-central-thesis.md](paper/01-central-thesis.md): why the report points beyond 3D archives.
- [paper/02-quality-and-purpose.md](paper/02-quality-and-purpose.md): fit-for-purpose quality, accuracy, precision, resolution.
- [paper/03-digitisation-as-process.md](paper/03-digitisation-as-process.md): planning, production, archive, sign-off.
- [paper/04-capture-methods.md](paper/04-capture-methods.md): photogrammetry, LiDAR, structured light, SLAM, GNSS, UAV, depth cameras.
- [paper/05-radiation-material-state.md](paper/05-radiation-material-state.md): thermal, multispectral, X-ray, terahertz, spectroscopy, RTI, photometric stereo.
- [paper/06-complexity.md](paper/06-complexity.md): object complexity, process complexity, environment, logistics.
- [paper/07-uncertainty.md](paper/07-uncertainty.md): uncertainty as the bridge to honest prediction.
- [paper/08-derived-data-formats-standards.md](paper/08-derived-data-formats-standards.md): derived data, formats, standards, interoperability.
- [paper/09-metadata-paradata.md](paper/09-metadata-paradata.md): provenance, process record, evidence/inference separation.
- [paper/10-bim-hbim-hhbim-digital-twins.md](paper/10-bim-hbim-hhbim-digital-twins.md): BIM, HBIM, HHBIM, and dynamic twins.
- [paper/11-ai-ml-and-future-tech.md](paper/11-ai-ml-and-future-tech.md): AI/ML, cloud, mobile LiDAR, XR, open data.

### Theory
- [theory/01-scan-as-state-estimate.md](theory/01-scan-as-state-estimate.md)
- [theory/02-semantic-3d-time-series.md](theory/02-semantic-3d-time-series.md)
- [theory/03-temporally-grounded-digital-twin.md](theory/03-temporally-grounded-digital-twin.md)
- [theory/04-generative-world-models.md](theory/04-generative-world-models.md)
- [theory/05-future-state-rendering.md](theory/05-future-state-rendering.md)
- [theory/06-uncertainty-visualization.md](theory/06-uncertainty-visualization.md)
- [theory/07-validation-loop.md](theory/07-validation-loop.md)

### Implementation
- [implementation/01-data-modalities.md](implementation/01-data-modalities.md)
- [implementation/02-pipeline-architecture.md](implementation/02-pipeline-architecture.md)
- [implementation/03-model-tool-landscape.md](implementation/03-model-tool-landscape.md)
- [implementation/04-agent-operating-guide.md](implementation/04-agent-operating-guide.md)
- [implementation/05-experiment-roadmap.md](implementation/05-experiment-roadmap.md)
- [implementation/06-basement-s0-alignment.md](implementation/06-basement-s0-alignment.md)

## Core Vocabulary
- **State estimate**: a measured, uncertain representation of a physical entity at a time.
- **4D evidence system**: a spatial-temporal graph linking sources, places, times, geometry, semantics, uncertainty, and renderable views.
- **Temporally grounded digital twin**: a state model linked to prior captures, current measurements, semantics, environment, and uncertainty.
- **Semantic 3D time series**: repeated registered captures whose geometry, material signals, and labels can be compared through time.
- **Rendered forecast**: a generated visualization of probable future physical states, constrained by measured state and transition assumptions.
- **Uncertainty field**: spatial, material, semantic, or temporal uncertainty attached to a model or forecast.
- **Probability defocus**: a visual language where uncertain future regions are rendered less sharply than stable regions.
- **Evidence / inference / visualization separation**: the discipline of tagging raw sensor evidence, derived interpretation, and presentation outputs as different epistemic objects.

## Non-Negotiable Framing
The future image is not a photograph; it is a visualization of a modeled probability distribution. The serious work is not generating the image. The serious work is constraining the image with measured reality and validating it against later captures.
