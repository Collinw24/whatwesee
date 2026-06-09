#!/usr/bin/env python3
"""Interactive 3DGS viewer for gsplat-mlx trained models.

Orbit the camera with keyboard, save screenshots. Designed for Apple Silicon.

Controls:
  Arrow keys    - Rotate camera (orbit)
  W/S           - Zoom in/out (dolly)
  A/D           - Pan left/right
  Q/E           - Roll
  R             - Reset camera
  S             - Save screenshot (docs/images/splat_view_###.png)
  ESC / Q close - Quit

Uses the non-differentiable NumPy reference rasterizer for speed.
"""

import json
import sys
from pathlib import Path

import cv2
import mlx.core as mx
import numpy as np
from scipy.spatial.transform import Rotation as R

from gsplat_mlx.rendering import rasterization


def load_params(npz_path: str) -> dict:
    """Load trained Gaussian params from .npz."""
    data = np.load(npz_path)
    return {
        "means": mx.array(data["means"]),
        "quats": mx.array(data["quats"]),
        "scales": mx.array(data["scales"]),
        "opacities": mx.array(data["opacities"]),
        "colors": mx.array(data["colors"]),
    }


def look_at_from_colmap(eye: np.ndarray, center: np.ndarray, up: np.ndarray) -> np.ndarray:
    """Build a COLMAP-convention view matrix matching the dataset convention.
    
    In COLMAP convention, the camera looks along +Z.
    We build R_w2c where: row0=right, row1=-up, row2=-forward (so +Z maps to forward).
    """
    forward = center - eye     # direction camera looks (world space)
    forward = forward / np.linalg.norm(forward)
    right = np.cross(up, forward)
    right = right / np.linalg.norm(right)
    cam_up = np.cross(forward, right)  # orthogonalized up
    
    # R_w2c: maps world coords to camera coords where camera looks along +Z
    # row0 = right (camera +X), row1 = cam_up (camera +Y), row2 = forward (camera +Z)
    viewmat = np.eye(4, dtype=np.float32)
    viewmat[0, :3] = right
    viewmat[1, :3] = cam_up
    viewmat[2, :3] = forward
    viewmat[0, 3] = -np.dot(right, eye)
    viewmat[1, 3] = -np.dot(cam_up, eye)
    viewmat[2, 3] = -np.dot(forward, eye)
    return viewmat


def build_K(width: int, height: int, fov_deg: float = 50.0) -> np.ndarray:
    """Build intrinsic matrix from FOV."""
    focal = (width / 2) / np.tan(np.radians(fov_deg) / 2)
    cx, cy = width / 2, height / 2
    K = np.array([[focal, 0, cx], [0, focal, cy], [0, 0, 1]], dtype=np.float32)
    return K


def render_view(params, viewmat, K, W, H):
    """Render the splat from a given camera."""
    rendered, _, _ = rasterization(
        means=params["means"],
        quats=params["quats"],
        scales=mx.exp(params["scales"]),
        opacities=mx.sigmoid(params["opacities"]),
        colors=params["colors"],
        viewmats=mx.array(viewmat[None]),
        Ks=mx.array(K[None]),
        width=W,
        height=H,
        render_mode="RGB",
        rasterize_mode="classic",
        differentiable=False,  # use NumPy ref rasterizer for speed
    )
    mx.eval(rendered)
    img = np.clip(np.array(rendered[0]), 0, 1)
    return (img * 255).astype(np.uint8)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Interactive 3DGS viewer for gsplat-mlx")
    parser.add_argument("--params", default="outputs/splat/final_params.npz")
    parser.add_argument("--center", nargs=3, type=float, help="Scene center x y z")
    parser.add_argument("--width", type=int, default=800)
    parser.add_argument("--height", type=int, default=600)
    parser.add_argument("--fov", type=float, default=55.0)
    args = parser.parse_args()
    
    print("Loading trained model...")
    params = load_params(args.params)
    N = params["means"].shape[0]
    print(f"Loaded {N:,} Gaussians")
    
    # Compute scene center
    means_np = np.array(params["means"])
    if args.center:
        center = np.array(args.center, dtype=np.float32)
    else:
        center = means_np.mean(axis=0).astype(np.float32)
    
    extent = np.ptp(means_np, axis=0).max()
    distance = extent * 1.5
    
    print(f"Scene center: {center}")
    print(f"Scene extent: {extent:.2f}, initial distance: {distance:.2f}")
    
    # Initial camera
    eye = center + np.array([0.0, -distance, distance * 0.3], dtype=np.float32)
    up = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    
    W, H = args.width, args.height
    K = build_K(W, H, args.fov)
    
    cv2.namedWindow("What We See — Gaussian Splat Viewer", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("What We See — Gaussian Splat Viewer", W, H)
    
    screenshot_idx = 0
    out_dir = Path("docs/images")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Movement parameters
    orbit_speed = 0.05      # radians per keypress
    zoom_speed = 0.15        # fraction of distance
    pan_speed_factor = 0.02  # fraction of extent
    
    print("\nControls:")
    print("  ← →      Orbit horizontally")
    print("  ↑ ↓      Orbit vertically")
    print("  W / S    Zoom in / out")
    print("  A / D    Pan left / right")
    print("  Q / E    Roll camera")
    print("  R        Reset view")
    print("  Space    Save screenshot")
    print("  ESC      Quit\n")
    
    needs_render = True
    frame = None
    
    while True:
        if needs_render:
            viewmat = look_at_from_colmap(eye, center, up)
            frame = render_view(params, viewmat, K, W, H)
            # BGR for OpenCV
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            needs_render = False
        
        cv2.imshow("What We See — Gaussian Splat Viewer", frame_bgr)
        key = cv2.waitKey(0) & 0xFF
        
        if key == 27:  # ESC
            break
        elif key == ord('q'):
            break
        
        needs_render = True
        
        # Orbit
        if key == 81:  # Left arrow
            rot = R.from_rotvec(up * orbit_speed)
            eye = center + rot.apply(eye - center)
        elif key == 83:  # Right arrow
            rot = R.from_rotvec(-up * orbit_speed)
            eye = center + rot.apply(eye - center)
        elif key == 82:  # Up arrow
            direction = eye - center
            right = np.cross(direction, up)
            right = right / np.linalg.norm(right)
            rot = R.from_rotvec(right * orbit_speed)
            eye = center + rot.apply(direction)
            up = rot.apply(up)
        elif key == 84:  # Down arrow
            direction = eye - center
            right = np.cross(direction, up)
            right = right / np.linalg.norm(right)
            rot = R.from_rotvec(-right * orbit_speed)
            eye = center + rot.apply(direction)
            up = rot.apply(up)
        
        # Zoom
        elif key == ord('w') or key == ord('W'):
            direction = eye - center
            dist = np.linalg.norm(direction)
            eye = center + direction / dist * max(dist * (1 - zoom_speed), extent * 0.1)
        elif key == ord('s') or key == ord('S'):
            direction = eye - center
            dist = np.linalg.norm(direction)
            eye = center + direction / dist * (dist * (1 + zoom_speed))
        
        # Pan
        elif key == ord('a') or key == ord('A'):
            direction = eye - center
            right = np.cross(direction, up)
            right = right / np.linalg.norm(right)
            offset = right * extent * pan_speed_factor
            center = center - offset
            eye = eye - offset
        elif key == ord('d') or key == ord('D'):
            direction = eye - center
            right = np.cross(direction, up)
            right = right / np.linalg.norm(right)
            offset = right * extent * pan_speed_factor
            center = center + offset
            eye = eye + offset
        
        # Roll
        elif key == ord('q') or key == ord('Q'):
            direction = eye - center
            direction = direction / np.linalg.norm(direction)
            rot = R.from_rotvec(direction * 0.1)
            up = rot.apply(up)
        elif key == ord('e') or key == ord('E'):
            direction = eye - center
            direction = direction / np.linalg.norm(direction)
            rot = R.from_rotvec(-direction * 0.1)
            up = rot.apply(up)
        
        # Reset
        elif key == ord('r') or key == ord('R'):
            eye = center + np.array([0.0, -distance, distance * 0.3], dtype=np.float32)
            up = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        
        # Screenshot
        elif key == ord(' '):
            path = out_dir / f"splat_view_{screenshot_idx:03d}.png"
            cv2.imwrite(str(path), frame_bgr)
            print(f"  📸 Saved: {path}")
            screenshot_idx += 1
            needs_render = False  # Don't re-render after screenshot
    
    cv2.destroyAllWindows()
    print(f"\nSaved {screenshot_idx} screenshots to {out_dir}/")


if __name__ == "__main__":
    main()
