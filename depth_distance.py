from dataclasses import dataclass
from math import isfinite, sqrt
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
    source: str = "ring"

    def as_dict(self):
        return {
            "z_mm": self.z_mm,
            "range_mm": self.range_mm,
            "x_mm": self.x_mm,
            "y_mm": self.y_mm,
            "valid_fraction": self.valid_fraction,
            "sample_count": self.sample_count,
            "source": self.source,
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
        hole_inner_ratio=0.35,
        hole_recess_mm=None,
    ):
        if min_mm < 0 or max_mm <= min_mm:
            raise ValueError("invalid depth range")
        if inner_ratio < 0 or outer_ratio <= inner_ratio:
            raise ValueError("outer_ratio must be larger than inner_ratio")
        if (
            not isfinite(hole_inner_ratio)
            or hole_inner_ratio <= 0
            or hole_inner_ratio >= inner_ratio
        ):
            raise ValueError(
                "hole_inner_ratio must be finite, positive, and smaller than inner_ratio"
            )
        if hole_recess_mm is not None and not isfinite(hole_recess_mm):
            raise ValueError("hole_recess_mm must be finite when configured")

        self.min_mm = float(min_mm)
        self.max_mm = float(max_mm)
        self.inner_ratio = float(inner_ratio)
        self.outer_ratio = float(outer_ratio)
        self.min_valid_samples = int(min_valid_samples)
        self.min_valid_fraction = float(min_valid_fraction)
        self.mad_scale = float(mad_scale)
        self.smoothing = float(smoothing)
        # Fallback sampling: when the ring around the hole (board surface) is
        # unavailable or too noisy, sample inside the hole opening instead and
        # correct with the field's fixed, signed recess offset:
        #   z_board_mm = z_hole_mm - hole_recess_mm
        # hole_recess_mm is None until measured on the real field, which
        # keeps the fallback disabled instead of guessing a distance.
        self.hole_inner_ratio = float(hole_inner_ratio)
        self.hole_recess_mm = None if hole_recess_mm is None else float(hole_recess_mm)
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

        estimate = self._estimate_z(depth_mm, box)
        if estimate is None:
            return None
        z_mm, valid_fraction, sample_count, source = estimate

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
            sample_count=sample_count,
            source=source,
        )

    def _estimate_z(self, depth_mm, box):
        # Primary: median depth of the board surface ring around the hole.
        # This is the original, unchanged behavior.
        ring_values, ring_fraction = self._ring_values(depth_mm, box)
        robust = self._robust_median(ring_values, ring_fraction)
        if robust is not None:
            z_mm, sample_count = robust
            return z_mm, ring_fraction, sample_count, "ring"

        # Fallback: the ring was unavailable or too noisy (reflection, glare,
        # partial occlusion). Sample inside the hole opening instead and
        # correct with the field's fixed recess offset, if it has been
        # calibrated. Without a calibrated offset we do not guess a distance.
        if self.hole_recess_mm is None:
            return None

        inner_values, inner_fraction = self._inner_values(depth_mm, box)
        robust = self._robust_median(inner_values, inner_fraction)
        if robust is None:
            return None

        hole_z_mm, sample_count = robust
        z_mm = hole_z_mm - self.hole_recess_mm
        if z_mm < self.min_mm or z_mm > self.max_mm:
            return None
        return z_mm, inner_fraction, sample_count, "hole_fallback"

    def _robust_median(self, values, valid_fraction):
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

        return float(np.median(values)), int(values.size)

    def _ring_values(self, depth_mm, box):
        return self._sample_region(depth_mm, box, self.inner_ratio, self.outer_ratio)

    def _inner_values(self, depth_mm, box):
        return self._sample_region(depth_mm, box, 0.0, self.hole_inner_ratio)

    def _sample_region(self, depth_mm, box, r_min, r_max):
        height, width = depth_mm.shape
        x1, y1, x2, y2 = [float(value) for value in box]
        cx = (x1 + x2) * 0.5
        cy = (y1 + y2) * 0.5
        rx = max((x2 - x1) * 0.5, 1.0)
        ry = max((y2 - y1) * 0.5, 1.0)

        left = max(0, int(np.floor(cx - rx * r_max)))
        right = min(width, int(np.ceil(cx + rx * r_max)) + 1)
        top = max(0, int(np.floor(cy - ry * r_max)))
        bottom = min(height, int(np.ceil(cy + ry * r_max)) + 1)
        if left >= right or top >= bottom:
            return np.empty(0, dtype=np.float32), 0.0

        yy, xx = np.ogrid[top:bottom, left:right]
        radius = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
        region_mask = (radius >= r_min) & (radius <= r_max)
        candidates = depth_mm[top:bottom, left:right][region_mask]
        if candidates.size == 0:
            return np.empty(0, dtype=np.float32), 0.0

        valid_mask = (
            np.isfinite(candidates)
            & (candidates >= self.min_mm)
            & (candidates <= self.max_mm)
        )
        values = candidates[valid_mask].astype(np.float32, copy=False)
        return values, float(values.size) / float(candidates.size)
