from dataclasses import dataclass
from math import sqrt
from typing import Dict, Optional, Tuple

import numpy as np


@dataclass(frozen=True)
class CameraIntrinsics:
    fx: float
    fy: float
    ppx: float
    ppy: float
    width: int
    height: int
    distortion_model: str = ""
    coeffs: Tuple[float, ...] = ()

    def as_dict(self):
        return {
            "fx": self.fx,
            "fy": self.fy,
            "ppx": self.ppx,
            "ppy": self.ppy,
            "width": self.width,
            "height": self.height,
            "distortion_model": self.distortion_model,
            "coeffs": self.coeffs,
        }


@dataclass(frozen=True)
class DepthMeasurement:
    z_mm: float
    range_mm: float
    x_mm: float
    y_mm: float
    valid_fraction: float
    sample_count: int

    def as_dict(self):
        return {
            "z_mm": self.z_mm,
            "range_mm": self.range_mm,
            "x_mm": self.x_mm,
            "y_mm": self.y_mm,
            "valid_fraction": self.valid_fraction,
            "sample_count": self.sample_count,
        }


class DepthEstimator:
    def __init__(
        self,
        min_mm=200,
        max_mm=8000,
        inner_ratio=0.60,
        outer_ratio=1.10,
        min_valid_samples=40,
        min_valid_fraction=0.20,
        mad_scale=3.5,
        smoothing=0.25,
    ):
        if min_mm < 0 or max_mm <= min_mm:
            raise ValueError("invalid depth range")
        if inner_ratio < 0 or outer_ratio <= inner_ratio:
            raise ValueError("outer_ratio must be larger than inner_ratio")

        self.min_mm = float(min_mm)
        self.max_mm = float(max_mm)
        self.inner_ratio = float(inner_ratio)
        self.outer_ratio = float(outer_ratio)
        self.min_valid_samples = int(min_valid_samples)
        self.min_valid_fraction = float(min_valid_fraction)
        self.mad_scale = float(mad_scale)
        self.smoothing = float(smoothing)
        self._smoothed_z: Dict[int, float] = {}

    def reset(self):
        self._smoothed_z.clear()

    def measure(
        self,
        depth_mm,
        box,
        center,
        intrinsics: CameraIntrinsics,
        target_id: Optional[int] = None,
    ) -> Optional[DepthMeasurement]:
        if depth_mm is None or intrinsics is None:
            return None
        if depth_mm.ndim != 2:
            raise ValueError("depth_mm must be a two-dimensional array")
        if intrinsics.fx <= 0 or intrinsics.fy <= 0:
            raise ValueError("camera focal lengths must be positive")

        values, valid_fraction = self._ring_values(depth_mm, box)
        if (
            values.size < self.min_valid_samples
            or valid_fraction < self.min_valid_fraction
        ):
            return None

        # Median + MAD removes flying pixels and background outliers without
        # changing the original detection, grid-ID, red-target, or selection logic.
        median = float(np.median(values))
        deviations = np.abs(values - median)
        mad = float(np.median(deviations))
        if mad > 0:
            robust_sigma = 1.4826 * mad
            values = values[deviations <= self.mad_scale * robust_sigma]
        if values.size < self.min_valid_samples:
            return None

        z_mm = float(np.median(values))
        if target_id is not None and 0.0 < self.smoothing < 1.0:
            previous = self._smoothed_z.get(int(target_id))
            if previous is not None:
                z_mm = previous + self.smoothing * (z_mm - previous)
            self._smoothed_z[int(target_id)] = z_mm

        cx, cy = center
        x_mm = (float(cx) - intrinsics.ppx) / intrinsics.fx * z_mm
        y_mm = (float(cy) - intrinsics.ppy) / intrinsics.fy * z_mm
        range_mm = sqrt(x_mm * x_mm + y_mm * y_mm + z_mm * z_mm)
        return DepthMeasurement(
            z_mm=z_mm,
            range_mm=range_mm,
            x_mm=x_mm,
            y_mm=y_mm,
            valid_fraction=valid_fraction,
            sample_count=int(values.size),
        )

    def _ring_values(self, depth_mm, box):
        height, width = depth_mm.shape
        x1, y1, x2, y2 = [float(value) for value in box]
        cx = (x1 + x2) * 0.5
        cy = (y1 + y2) * 0.5
        rx = max((x2 - x1) * 0.5, 1.0)
        ry = max((y2 - y1) * 0.5, 1.0)

        left = max(0, int(np.floor(cx - rx * self.outer_ratio)))
        right = min(width, int(np.ceil(cx + rx * self.outer_ratio)) + 1)
        top = max(0, int(np.floor(cy - ry * self.outer_ratio)))
        bottom = min(height, int(np.ceil(cy + ry * self.outer_ratio)) + 1)
        if left >= right or top >= bottom:
            return np.empty(0, dtype=np.float32), 0.0

        yy, xx = np.ogrid[top:bottom, left:right]
        radius = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
        ring_mask = (radius >= self.inner_ratio) & (radius <= self.outer_ratio)
        candidates = depth_mm[top:bottom, left:right][ring_mask]
        if candidates.size == 0:
            return np.empty(0, dtype=np.float32), 0.0

        valid_mask = (
            np.isfinite(candidates)
            & (candidates >= self.min_mm)
            & (candidates <= self.max_mm)
        )
        values = candidates[valid_mask].astype(np.float32, copy=False)
        return values, float(values.size) / float(candidates.size)
