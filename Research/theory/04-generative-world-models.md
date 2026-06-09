# Generative World Models

## Purpose
Define how generative models fit into the project without overstating their capability.

## Core Claim
A generative world model does not know the future. It learns or encodes a probability distribution over future states conditioned on prior observations, material behavior, physical constraints, environment, and context.

## Agent Takeaways
- Use generative models as conditional state-transition tools, not as unconstrained image makers.
- Prediction should operate on state, not only pixels.
- Outputs must be ensembles or uncertainty-aware forecasts.
- Validate by comparing predicted states against later measured states.

## Paper Grounding
- Section 5.9, report p. 87: AI/ML can classify features, enrich metadata/paradata, analyze high-dimensional data, support predictions, and enable near-real-time responses.
- Section 3.12.1, report p. 71: uncertainty and repeated observations are part of measurement quality.
- Section 5.6, report p. 86: digital twins connect virtual state to real-world dynamics.

## Transition Dynamics
```text
P(S_t+1 | S_t, S_t-1, environment, material_state, constraints)
```

The model estimates probable next states. It may use:

- learned patterns from prior scans;
- physical constraints;
- material-specific behavior;
- environmental histories;
- expert priors;
- simulation results;
- observed change rates.

For forecast media, a clearer expression is:

```text
rendered image ~ visualization(P(S_t+h | measured state, prior states, environment, material constraints, scenario))
```

The image is a sample, summary, or view of a distribution. It is not the distribution itself and not a measured future state.

## Model Roles
| Role | Example |
| --- | --- |
| Completion | infer hidden or occluded geometry with uncertainty. |
| Denoising | reduce sensor noise while preserving uncertainty. |
| Segmentation | label components, defects, materials, and regions. |
| Change modeling | learn geometric or material-state transitions. |
| Forecast rendering | visualize plausible future states. |

## Scenario Engines
World models become more useful when they are scenario engines rather than open-ended generators. Autonomous-driving research is a useful analogy because it separates measured state, maps, actor behavior, scenario description, rollout, and validation. Sources such as [Waymax](https://waymo.com/research/waymax/), [nuPlan](https://arxiv.org/abs/2106.11810), and [ASAM OpenSCENARIO](https://report.asam.net/asam-openscenario) are not heritage methods, but they show a mature pattern: generate futures under explicit conditions, then score them.

For this project, scenario variables might include:

- rainfall and humidity history;
- UV/light exposure;
- freeze/thaw cycles;
- repair or no-repair intervention;
- vibration/load profile;
- material class and known decay mechanisms;
- geospatial exposure and historical repair record.

The project should avoid prompt-only future rendering. The scenario should bind a forecast to measured state, assumptions, and a validation target.

## Physics-Constrained And Radiance-Field Models
Radiance-field methods can support playback of observed change, and physics-constrained neural methods point toward richer transition models. [PAC-NeRF](https://arxiv.org/abs/2303.05512) is conceptually relevant because it couples a radiance-field representation with differentiable physics for system identification. That is not yet a general conservation or infrastructure forecasting system, but it supports the design principle: predict physical/material state first, then render the state.

Dynamic radiance fields and 4D Gaussian splats belong here as representation and rendering layers for temporal states. They should not be treated as the complete twin, the complete archive, or the source of physical certainty.

## Future-State Imaging Implication
The generated image is the last layer of the system, not the first. It should be generated from a predicted state, such as a deformed mesh, changed texture field, crack-propagation map, moisture probability, thermal anomaly, or restored-state hypothesis.

## Evidence / Inference / Visualization
- Evidence constrains the current state.
- Inference estimates the transition.
- Visualization renders the forecast.

## Practical Rule
Prefer an ugly forecast with calibrated uncertainty over a beautiful forecast with no evidential discipline.
