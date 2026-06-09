# Capture Guide

The pipeline can ingest mixed cameras, lenses, focal lengths, and angles, but reconstruction quality still depends mostly on capture discipline. The goal is consistent overlap, enough texture for feature matching, and complete coverage.

## Shared Rules

- Shoot high resolution stills, not heavily compressed social-media exports.
- For Canon cameras, shoot RAW+JPEG when possible. The pipeline archives `.CR2`/`.CR3` originals and uses JPEGs as the first working set for COLMAP/Nerfstudio. RAW-only captures can be converted to full-resolution JPEG working images later.
- For iPhone captures, keep the `.HEIC` originals but normalize them to full-resolution JPEG quality 100 before reconstruction.
- Keep 70-85% overlap between adjacent photos.
- Move the camera, do not stand still and zoom.
- Lock exposure, focus, and white balance for each capture pass when possible.
- Avoid motion blur. Use a fast shutter or tripod.
- Keep EXIF intact. Do not strip camera, lens, focal length, or timestamp metadata.
- Capture matte, textured surfaces more aggressively than shiny, transparent, or featureless surfaces.
- Use diffuse lighting. Avoid harsh moving shadows and blown highlights.
- Include scale references or markers if real-world dimensions matter.
- Do not mix edited and unedited copies of the same photo in one dataset.

## Object Capture

Use this for products, artifacts, props, small structures, and standalone physical things.

Minimum useful capture:

- 40-80 photos for a simple object.
- 100-250 photos for detailed, concave, glossy, or asymmetric objects.
- Three rings around the object: low, mid, high.
- Extra close-ups for high-detail regions.

Best practice:

- Put the object on a non-reflective surface.
- Use a plain but feature-rich enough background, or use masks later.
- Keep the object fixed and move around it.
- Capture the underside separately if it matters.
- Add cross-polarized lighting for shiny objects when possible.

Common failures:

- Too few views from above or below.
- Turntable captures where the background dominates feature matching.
- Large exposure changes between rings.
- Transparent, mirror-like, black, or pure white surfaces without controlled lighting.

## Space Capture

Use this for rooms, interior scenes, outdoor areas, and navigable environments.

Minimum useful capture:

- 80-150 photos for a small room.
- 200-600 photos for large interiors or dense detail.
- Multiple height passes: waist height, eye height, and high/low detail passes.
- Photos around corners, doorways, and occluded areas.

Best practice:

- Walk a loop and close the loop with overlapping views.
- Add transition shots between rooms.
- Capture each wall from oblique angles, not just straight-on shots.
- Avoid large blank walls as the only overlap between shots.
- Keep moving objects out of the scene.

Common failures:

- Long corridors with repetitive features.
- Featureless white walls.
- Mirrors and windows creating false geometry.
- Photos taken too far apart.
- Mixed day/night or lights-on/lights-off passes.

## Indoor Garden Capture

Use the `mixed` dataset type for an indoor garden because it has both object-like subjects and room/space context.

Recommended first test:

- 120-250 RAW+JPEG photos.
- One wide establishing loop around the garden area.
- One mid-height loop around each bed, shelf, tent, or cluster.
- Close detail passes for dense foliage, trellis structure, labels, pots, irrigation, lights, and wall/floor context.
- Keep grow lights fixed for the whole capture. Do not mix lights-on and lights-off passes.
- Turn off fans, pumps, and anything else that moves leaves or water.
- Add a few scale references such as a ruler, marker board, or known-size pot.
- Avoid brushing plants between shots; foliage movement is a major reconstruction failure mode.

## Mixed Cameras and Lenses

Mixed capture is supported, but it increases calibration complexity.

- Keep full EXIF for every image.
- Prefer one camera/lens/focal length per pass.
- Avoid variable zoom during a single continuous pass.
- If using a zoom lens, stop at known focal lengths and capture complete mini-rings at each focal length.
- Do not combine very wide fisheye shots and narrow telephoto shots unless the dataset needs both.

## Field Checklist

- Capture raw originals and a JPEG set when possible.
- Verify the first 10-20 photos are sharp before completing the whole scan.
- Photograph a slate or note card with dataset name, date, camera, and target.
- Keep each capture session in its own folder before ingest.
- Do not delete rejected photos until the pipeline has produced a final report.
