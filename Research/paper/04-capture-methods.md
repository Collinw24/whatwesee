# Capture Methods

## Purpose
Summarize the report's survey of documentation methods and explain why no single capture method is enough for future-state imaging.

## Core Claim
Each capture method samples a different relationship between the sensor and the physical world. A serious system combines instruments according to scale, material, accuracy, texture, access, speed, cost, and failure modes.

## Agent Takeaways
- Do not seek one universal scanner.
- Choose capture methods based on intended use and measurable failure modes.
- Use overlapping modalities where prediction requires geometry, material state, and condition.
- Registration is the hinge that makes multiple methods useful together.

## Paper Grounding
- Section 2.4, report pp. 8-11: documentation methods range from tactile measurement to GNSS, total station, LiDAR, photogrammetry, X-ray, and infrared.
- Section 2.5, report pp. 12-16: active systems include TLS, structured light, optical triangulation, depth/range cameras, and SLAM; passive systems include photogrammetry, aerial imagery, close-range photography, and video frame extraction.
- Section 2.7-2.9, report pp. 19-21: capture quality depends on access, environment, distance, angle of incidence, reflectivity, transmittance, and surface condition.

## Method Families
| Family | Strength | Typical weakness |
| --- | --- | --- |
| Manual/tactile | Simple measurements, checks, small details | Sparse, slow, limited coverage. |
| GNSS/total station | Control networks, georeferencing, scale | Sparse point measurement. |
| Terrestrial laser scanning | Dense geometry for buildings/sites | Occlusion, reflectivity, registration burden. |
| Mobile laser scanning | Fast coverage and mobility | Accuracy and drift concerns. |
| UAV/aerial capture | roofs, terrain, large areas | regulation, weather, GCP requirements. |
| Photogrammetry/SfM/MVS | accessible, texture-rich, flexible | lighting, overlap, scale, reflective/transparent surfaces. |
| Structured light/triangulation | high-detail small objects | limited field, lighting sensitivity. |
| Depth/range cameras | fast RGB-D capture | often visualization-grade unless carefully validated. |
| SLAM | pose plus mapping during motion | drift, feature dependence, dynamic-scene problems. |

## Current Reconstruction Layer
The capture method is not the whole method. Modern reconstruction stacks now include classical survey tools and learned models:

- COLMAP/GLOMAP/OpenMVS/RealityCapture/Metashape for SfM/MVS and production photogrammetry;
- LiDAR/TLS registration and scan-to-mesh/scan-to-BIM workflows;
- DUSt3R, MASt3R, VGGT, and related foundation models for camera/depth/point-map estimation;
- NeRFs and Gaussian splats for view synthesis and inspection;
- dynamic NeRF/4D Gaussian methods for observed temporal playback.

These are derived inference or visualization layers unless their outputs are checked against calibration, scale, control, and later validation. Agents should preserve the raw capture and reconstruction provenance rather than treating the final representation as the original evidence.

## Future-State Imaging Implication
Prediction needs different evidence channels:

- geometry for deformation and crack growth;
- texture for surface change;
- thermal/IR for hidden moisture or heat anomalies;
- spectra for material state;
- environmental sensors for transition drivers.

The purpose is not to maximize data. The purpose is to capture the minimum sufficient state vector for the physical transition being studied.

## Evidence / Inference / Visualization
The same surface may be represented as raw images, point cloud, mesh, depth map, Gaussian splat, and semantic object. Agents must keep the instrument origin attached to every derived representation.
