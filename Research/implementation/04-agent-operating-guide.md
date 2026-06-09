# Agent Operating Guide

## Purpose
Give future agents a compact operating protocol for working on this project without losing the research discipline.

## Core Claim
Agents should treat this project as an evidence-constrained physical-state modeling system. The objective is not to make compelling images first; it is to build the conditions under which compelling future-state images are technically meaningful.

## Agent Takeaways
- Read [../README.md](../README.md), [../paper/00-paper-map.md](../paper/00-paper-map.md), and [../theory/01-scan-as-state-estimate.md](../theory/01-scan-as-state-estimate.md) before planning new work.
- Use [../../photogrammetry/docs/capture-guide.md](../../photogrammetry/docs/capture-guide.md) for image capture discipline.
- Preserve raw evidence, metadata, paradata, and uncertainty.
- Never claim literal capture of tomorrow.
- Treat Time Machine, Europeana, EUreka3D, and 3DBigDataSpace as infrastructure precedents, not permission to skip validation.

## Paper Grounding
- Section 2.3, report pp. 6-7: project planning and process documentation are required.
- Section 3.12.1, report p. 71: uncertainty sources must be acknowledged.
- Section 4.4, report pp. 79-82: interoperability and preservation depend on metadata and process information.
- Section 5.9, report p. 87: AI/ML should support classification, enrichment, prediction, and monitoring.

## Working Protocol
1. Identify the physical target and intended use.
2. Define the state variables that matter: geometry, appearance, material, thermal, spectral, environmental, semantic.
3. Define capture protocol and repeat interval.
4. Ingest and preserve raw evidence.
5. Produce working derivatives with provenance.
6. Register all outputs into a stable coordinate frame.
7. Create semantic labels and uncertainty fields.
8. Compare against prior states.
9. Produce a conservative forecast only after change evidence exists.
10. Validate the forecast against the next capture.

## Research Loop Protocol
When asked to expand the research corpus:

1. Select one topic and keep the synthesis narrow.
2. Gather canonical sources, adjacent/fringe leads, technical methods, and counterweights.
3. Label source reliability: `primary`, `peer-reviewed`, `credible secondary`, or `exploratory`.
4. Update existing Research markdown files only unless the user explicitly asks for new files.
5. Do not let speculative sources override the project rule: future images are rendered forecasts constrained by measured reality.
6. Where a source describes a tool, dataset, or model, record limitations and validation needs.

## Required Language
Use:

- state estimate;
- temporally grounded digital twin;
- rendered forecast;
- measured reality;
- uncertainty field;
- ensemble of plausible trajectories;
- world model constrained by sensor evidence.

Avoid:

- literal capture of tomorrow;
- certainty without validation;
- claims that AI knows or sees the future;
- treating generated imagery as evidence.

## Evidence / Inference / Visualization
When writing docs, code comments, reports, or UI labels, explicitly name which layer an artifact belongs to:

- `evidence`: measured sensor input;
- `inference`: derived reconstruction, classification, prediction;
- `visualization`: human-facing render or explanation.

Use the evidence taxonomy where helpful:

- `observed`;
- `measured`;
- `documented`;
- `inferred`;
- `analogical`;
- `hypothetical`;
- `AI-suggested`.

An AI output may become evidence only after it is independently measured, verified, or promoted through a documented review/validation step. Until then it remains inference or visualization.

## Future-State Imaging Implication
Any agent asked to generate a future image should first ask whether there is a current state estimate, prior state, transition assumption, and uncertainty representation. If not, the correct task is to create a conceptual or illustrative image, not a rendered forecast.

## Quality Gate
Before marking work complete, check:

- source PDF remains intact;
- relative links resolve;
- paper claims have section/page grounding;
- external model/tool claims link to primary docs where practical;
- forecast language includes uncertainty and validation.
- local-source basenames mentioned by the task are represented in the corpus.
- external links resolve or are clearly marked as research leads.
- no text implies unmeasured future capture, certainty without validation, or unvalidated AI foresight.
