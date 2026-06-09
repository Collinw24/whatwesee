# Quality And Purpose

## Purpose
Capture the report's quality framework: quality is not visual beauty, but fitness for a declared use under known accuracy, precision, resolution, and uncertainty limits.

## Core Claim
A high-quality scan for public viewing may be inadequate for structural monitoring. A high-resolution model may still be metrically weak. Quality only becomes meaningful when tied to intended use.

## Agent Takeaways
- Always ask what the scan is for before judging quality.
- Preserve accuracy, precision, and resolution as separate fields in data models.
- Do not use visually convincing outputs as substitutes for metric evidence.
- For prediction, quality must include repeatability and uncertainty, not just appearance.

## Paper Grounding
- Section 2.1, report pp. 4-5: different 3D uses include structural assessment, 3D printing, creative industry, XR, repositories, education, and public access.
- Section 2.2, report p. 6: accuracy is closeness to true value; precision is repeatability; the terms are often confused.
- Section 2.4, report pp. 8-9: level of detail must be established at the start and may vary by feature or project purpose.
- Section 3.11-3.12, report pp. 67-70: quality includes geometry, radiometry/photometry, completeness, material, structural health, texture, scale, and spectral layers.

## Key Distinctions
| Term | Meaning | Failure mode |
| --- | --- | --- |
| Accuracy | Closeness to truth or accepted reference | A precise but biased scanner can be inaccurate. |
| Precision | Repeatability of measurements | Repeated values can agree with each other while being wrong. |
| Resolution | Smallest sampled detail/granularity | Fine detail can be captured at the wrong scale. |
| Completeness | Coverage of the required physical surface/state | Occlusion or access gaps can hide important evidence. |
| Fidelity | Faithfulness of color, texture, material, or reflectance | A nice render can erase sensor limits. |

## Future-State Imaging Implication
Prediction needs a stronger quality definition than display. A rendered forecast can only be scored if the current and future states are metrically comparable. That requires:

- stable coordinate frames;
- known scale;
- comparable capture settings;
- repeatable registration;
- documented processing;
- explicit uncertainty fields.

## Data-Space Quality Is Not Enough
Europeana-style tiers, FAIR principles, and embeddable 3D viewers are useful publication checks, but they do not by themselves establish predictive quality. A model can be findable, accessible, interoperable, reusable, and visually polished while still being unsuitable for change detection.

For future-state imaging, quality also requires:

- declared state variables;
- metric or material accuracy requirements;
- repeat-capture comparability;
- source confidence and paradata;
- validation metrics for later observations;
- rights and access clarity for reuse by agents.

Use data-space quality as a publication floor, not as the scientific ceiling.

## Evidence / Inference / Visualization
- Evidence: calibrated measurements and raw sensor data.
- Inference: derived geometry, material labels, condition assessments.
- Visualization: rendered images, meshes for display, splats, XR views.

If a generated future image is visually sharp but its inputs were low-accuracy or poorly registered, the image can be persuasive while being scientifically weak.

## Practical Rule
Define quality as:

```text
quality = fitness_for_declared_use + known_error_limits + preserved_provenance
```

For this project, the declared use is not only archive or display. It is future-state rendering from a temporally grounded digital twin.
