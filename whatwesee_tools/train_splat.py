#!/usr/bin/env python3
"""Train 3D Gaussian Splatting on COLMAP data using gsplat-mlx (Apple Silicon).

Loads a nerfstudio-formatted dataset (images + transforms.json with COLMAP poses),
initializes Gaussians from the COLMAP sparse point cloud, and trains via the
differentiable pure-MLX rasterizer.
"""

import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import mlx.core as mx
import numpy as np
from PIL import Image

from gsplat_mlx.rendering import rasterization
from gsplat_mlx.core.covariance import quat_scale_to_covar_preci
from gsplat_mlx.core.spherical_harmonics import spherical_harmonics


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_nerfstudio_dataset(data_dir: str, max_size: int = 800) -> dict:
    """Load images and camera poses from a nerfstudio-processed dataset."""
    data_dir = Path(data_dir)
    
    with open(data_dir / "transforms.json") as f:
        transforms = json.load(f)
    
    frames = transforms["frames"]
    
    # Get dimensions from first frame
    first = frames[0]
    w, h = first["w"], first["h"]
    
    # Determine downscale
    scale = min(1.0, max_size / max(w, h))
    new_w, new_h = int(w * scale), int(h * scale)
    
    images = []
    viewmats = []
    Ks = []
    
    for frame in frames:
        img_path = data_dir / frame["file_path"]
        if not img_path.exists():
            continue
        
        img = Image.open(img_path)
        if scale < 1.0:
            img = img.resize((new_w, new_h), Image.LANCZOS)
        img_array = np.array(img, dtype=np.float32) / 255.0
        images.append(mx.array(img_array))
        
        # Camera extrinsics (world-to-camera)
        tf = np.array(frame["transform_matrix"], dtype=np.float32)
        viewmats.append(mx.array(tf))
        
        # Intrinsics (adjusted for downscale)
        fl_x = frame["fl_x"] * scale
        fl_y = frame["fl_y"] * scale
        cx = frame["cx"] * scale
        cy = frame["cy"] * scale
        K = np.array([[fl_x, 0, cx], [0, fl_y, cy], [0, 0, 1]], dtype=np.float32)
        Ks.append(mx.array(K))
    
    print(f"Loaded {len(images)} images at {new_w}x{new_h}")
    return {
        "images": images,
        "viewmats": mx.stack(viewmats),
        "Ks": mx.stack(Ks),
        "width": new_w,
        "height": new_h,
    }


def load_colmap_sparse_ply(ply_path: str, num_gaussians: int = 50000) -> dict:
    """Initialize Gaussians from COLMAP sparse point cloud."""
    import open3d as o3d
    
    pcd = o3d.io.read_point_cloud(str(ply_path))
    pts = np.asarray(pcd.points)
    colors = np.asarray(pcd.colors) if pcd.has_colors() else np.ones((len(pts), 3)) * 0.5
    
    # Sample to target count
    if len(pts) > num_gaussians:
        idx = np.random.choice(len(pts), num_gaussians, replace=False)
        pts = pts[idx]
        colors = colors[idx]
    
    N = len(pts)
    print(f"Initialized {N} Gaussians from COLMAP sparse cloud")
    
    # Center the point cloud
    center = pts.mean(axis=0)
    pts_centered = pts - center
    
    # Estimate initial scale from point spacing
    if N > 1:
        from scipy.spatial import cKDTree
        tree = cKDTree(pts_centered)
        # Average distance to 3 nearest neighbors (skip self)
        dists, _ = tree.query(pts_centered, k=4)
        avg_spacing = dists[:, 1:].mean()
    else:
        avg_spacing = 0.1
    
    init_scale = np.log(avg_spacing * 1.5)
    
    return {
        "means": mx.array(pts_centered.astype(np.float32)),
        "quats": mx.array(np.column_stack([np.ones(N), np.zeros((N, 3))]).astype(np.float32)),
        "scales": mx.array(np.full((N, 3), init_scale, dtype=np.float32)),
        "opacities": mx.array(np.full(N, 0.0, dtype=np.float32)),  # sigmoid(0) = 0.5
        "colors": mx.array(colors.astype(np.float32)),
    }


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_step(
    params: Dict[str, mx.array],
    viewmats: mx.array,
    Ks: mx.array,
    target_images: mx.array,
    width: int,
    height: int,
    batch_size: int = 1,
) -> Tuple[mx.array, Dict[str, mx.array]]:
    """Single training step with batch of images."""
    
    # Select random batch
    N_cameras = viewmats.shape[0]
    batch_idx = np.random.choice(N_cameras, batch_size, replace=False).astype(np.int32)
    batch_viewmats = viewmats[mx.array(batch_idx)]
    batch_Ks = Ks[mx.array(batch_idx)]
    batch_targets = target_images[mx.array(batch_idx)]
    
    def loss_fn(means, quats, scales, opacities, colors):
        # Apply activations
        scales_exp = mx.exp(scales)
        opacities_sig = mx.sigmoid(opacities)
        
        # Render
        rendered, _, _ = rasterization(
            means=means,
            quats=quats,
            scales=scales_exp,
            opacities=opacities_sig,
            colors=colors,
            viewmats=batch_viewmats,
            Ks=batch_Ks,
            width=width,
            height=height,
            render_mode="RGB",
            rasterize_mode="classic",
        )
        
        # L1 loss
        loss = mx.mean(mx.abs(rendered - batch_targets))
        return loss
    
    loss, grads = mx.value_and_grad(loss_fn, argnums=(0, 1, 2, 3, 4))(
        params["means"], params["quats"], params["scales"],
        params["opacities"], params["colors"],
    )
    mx.eval(loss)
    
    return loss, {
        "means": grads[0],
        "quats": grads[1],
        "scales": grads[2],
        "opacities": grads[3],
        "colors": grads[4],
    }


def train(
    dataset: dict,
    params: dict,
    num_steps: int = 2000,
    lr: float = 1e-2,
    save_every: int = 200,
    output_dir: str = "outputs/splat",
):
    """Full training loop."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    images = mx.stack(dataset["images"])
    viewmats = dataset["viewmats"]
    Ks = dataset["Ks"]
    W, H = dataset["width"], dataset["height"]
    
    param_lrs = {
        "means": lr * 1.0,
        "quats": lr * 0.1,
        "scales": lr * 0.5,
        "opacities": lr * 0.5,
        "colors": lr * 0.5,
    }
    
    # Adam state
    beta1, beta2, eps = 0.9, 0.999, 1e-8
    adam_state = {}
    param_names = ["means", "quats", "scales", "opacities", "colors"]
    
    print(f"\nTraining {len(params['means'])} Gaussians on {len(dataset['images'])} images "
          f"({W}x{H}) for {num_steps} steps")
    print(f"Device: MLX on Apple Silicon")
    print(f"{'─'*60}")
    
    losses = []
    t0 = time.time()
    
    for step in range(num_steps):
        loss, grads = train_step(params, viewmats, Ks, images, W, H, batch_size=1)
        loss_val = loss.item()
        losses.append(loss_val)
        
        # Adam update
        for name in param_names:
            p = params[name]
            g = grads[name]
            plr = param_lrs[name]
            
            if name not in adam_state:
                adam_state[name] = {"step": 0, "m": mx.zeros_like(p), "v": mx.zeros_like(p)}
            
            s = adam_state[name]
            s["step"] += 1
            t_step = s["step"]
            
            s["m"] = beta1 * s["m"] + (1 - beta1) * g
            s["v"] = beta2 * s["v"] + (1 - beta2) * g * g
            
            m_hat = s["m"] / (1 - beta1 ** t_step)
            v_hat = s["v"] / (1 - beta2 ** t_step)
            
            params[name] = p - plr * m_hat / (mx.sqrt(v_hat) + eps)
        
        # Evaluate
        mx.eval(*[params[n] for n in param_names])
        mx.eval(*[adam_state[n]["m"] for n in param_names], *[adam_state[n]["v"] for n in param_names])
        
        if step % 50 == 0 or step == num_steps - 1:
            elapsed = time.time() - t0
            eta = (elapsed / (step + 1)) * (num_steps - step - 1) if step > 0 else 0
            print(f"  Step {step:5d}/{num_steps} | Loss: {loss_val:.4f} | "
                  f"Time: {elapsed:.0f}s | ETA: {eta:.0f}s")
        
        if (step + 1) % save_every == 0:
            _save_render(params, viewmats[0:1], Ks[0:1], W, H, output_dir, step + 1)
    
    # Final save
    print(f"\n{'─'*60}")
    print(f"Final loss: {losses[-1]:.4f} (start: {losses[0]:.4f})")
    if losses[0] > 0:
        print(f"Reduction: {(1 - losses[-1]/losses[0])*100:.1f}%")
    
    # Save final params
    _save_params(params, output_dir / "final_params.npz")
    _save_render(params, viewmats[0:1], Ks[0:1], W, H, output_dir, "final")
    
    return losses


def _save_render(params, viewmat, K, W, H, out_dir, tag):
    """Render a single view and save as PNG."""
    rendered, _, _ = rasterization(
        means=params["means"],
        quats=params["quats"],
        scales=mx.exp(params["scales"]),
        opacities=mx.sigmoid(params["opacities"]),
        colors=params["colors"],
        viewmats=viewmat,
        Ks=K,
        width=W,
        height=H,
        render_mode="RGB",
        rasterize_mode="classic",
    )
    mx.eval(rendered)
    img = np.clip(np.array(rendered[0]), 0, 1)
    img_uint8 = (img * 255).astype(np.uint8)
    out_path = out_dir / f"render_{tag}.png"
    Image.fromarray(img_uint8).save(out_path)
    print(f"  Saved render: {out_path}")


def _save_params(params, path):
    """Save params as numpy dict."""
    np_params = {k: np.array(v) for k, v in params.items()}
    np.savez_compressed(path, **np_params)
    print(f"  Saved params: {path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Train 3DGS on Apple Silicon with gsplat-mlx")
    parser.add_argument("--data", required=True, help="Nerfstudio dataset directory")
    parser.add_argument("--colmap-sparse", help="Path to COLMAP sparse PLY for init")
    parser.add_argument("--num-gaussians", type=int, default=30000)
    parser.add_argument("--num-steps", type=int, default=2000)
    parser.add_argument("--max-size", type=int, default=400, help="Max image dimension")
    parser.add_argument("--lr", type=float, default=1e-2)
    parser.add_argument("--output-dir", default="outputs/splat")
    parser.add_argument("--save-every", type=int, default=200)
    
    args = parser.parse_args()
    
    print("Loading dataset...")
    dataset = load_nerfstudio_dataset(args.data, args.max_size)
    
    if args.colmap_sparse:
        params = load_colmap_sparse_ply(args.colmap_sparse, args.num_gaussians)
    else:
        print("No COLMAP sparse PLY provided, using random init", file=sys.stderr)
        sys.exit(1)
    
    train(dataset, params, args.num_steps, args.lr, args.save_every, args.output_dir)
