from __future__ import annotations

import numpy as np
from scipy import stats as scipy_stats

from src.models import AnomalyResult


# ─── Individual Detection Methods ─────────────────────────────────────────────

def zscore_detect(values: list[float], threshold: float = 3.0) -> list[int]:
    """Modified Z-score using median and MAD for robustness against the spike
    inflating mean/std (classic Z-score pitfall on small samples)."""
    if len(values) < 3:
        return []
    arr = np.array(values, dtype=float)
    median = float(np.median(arr))
    mad = float(np.median(np.abs(arr - median)))
    # MAD-based modified Z-score (Iglewicz & Hoaglin 1993)
    # 0.6745 is the 75th percentile of the standard normal distribution
    consistency = mad / 0.6745 if mad > 0 else (float(np.std(arr)) or 1.0)
    return [i for i, v in enumerate(values) if abs((v - median) / consistency) > threshold]


def iqr_detect(values: list[float], factor: float = 1.5) -> list[int]:
    """Return indices outside [Q1 − factor·IQR, Q3 + factor·IQR].
    When IQR=0 (uniform normal data), falls back to 10% of median as minimum scale."""
    if len(values) < 4:
        return []
    arr = np.array(values, dtype=float)
    q1, q3 = float(np.percentile(arr, 25)), float(np.percentile(arr, 75))
    iqr = q3 - q1
    if iqr == 0:
        # All values equal — use 10% of median as minimum scale, or std
        median = float(np.median(arr))
        iqr = max(median * 0.1, float(np.std(arr)), 1.0)
    lower, upper = q1 - factor * iqr, q3 + factor * iqr
    return [i for i, v in enumerate(values) if v < lower or v > upper]


def sliding_window_detect(
    values: list[float], window: int = 3, threshold: float = 3.0
) -> list[int]:
    """Return indices that deviate > *threshold* std-devs from the preceding window mean.
    Uses a smaller default window (3) so it fires on early spikes in short series."""
    n = len(values)
    if n <= window:
        # Fall back to comparing each value vs overall median
        median = float(np.median(values))
        mad = float(np.median(np.abs(np.array(values) - median))) or 1.0
        return [i for i, v in enumerate(values) if abs(v - median) / mad > threshold]
    anomalies: list[int] = []
    for i in range(window, n):
        w = np.array(values[i - window : i], dtype=float)
        w_mean = float(np.mean(w))
        w_std = float(np.std(w)) or (w_mean * 0.05) or 1.0
        if abs(values[i] - w_mean) / w_std > threshold:
            anomalies.append(i)
    return anomalies


# ─── Trend Detection ──────────────────────────────────────────────────────────

def detect_trend(values: list[float]) -> dict:
    """Linear regression over *values*. Returns direction and slope."""
    if len(values) < 3:
        return {"direction": "stable", "slope": 0.0}
    x = np.arange(len(values), dtype=float)
    y = np.array(values, dtype=float)
    slope, _, _, _, _ = scipy_stats.linregress(x, y)
    slope = float(slope)
    direction = "up" if slope > 1.0 else "down" if slope < -1.0 else "stable"
    return {"direction": direction, "slope": round(slope, 4)}


# ─── Severity Classification ──────────────────────────────────────────────────

def classify_severity(values: list[float], anomaly_indices: set[int]) -> str:
    """Classify severity by how much the anomalous value deviates from normal."""
    if not anomaly_indices:
        return "none"
    normal_vals = [v for i, v in enumerate(values) if i not in anomaly_indices]
    if not normal_vals:
        return "low"
    normal_mean = float(np.mean(normal_vals)) or 1.0
    max_anomaly = max(values[i] for i in anomaly_indices)
    ratio = max_anomaly / normal_mean
    if ratio >= 10:
        return "critical"
    if ratio >= 5:
        return "high"
    if ratio >= 2:
        return "medium"
    return "low"


# ─── Main Detector Class ──────────────────────────────────────────────────────

class AnomalyDetector:
    """Ensemble anomaly detector using three statistical methods.

    A point is flagged as an anomaly only when ≥2 of the three methods agree,
    reducing false-positive rate compared to any single method alone.
    """

    def __init__(
        self,
        zscore_threshold: float = 3.0,
        iqr_factor: float = 1.5,
        window_size: int = 5,
    ):
        self.zscore_threshold = zscore_threshold
        self.iqr_factor = iqr_factor
        self.window_size = window_size

    def detect(self, metrics: list[dict]) -> AnomalyResult:
        """Detect anomalies in *metrics*.

        Each metric dict must contain a ``latency_ms`` key.
        Optionally also checks ``rows_scanned`` if present.
        """
        if not metrics:
            return AnomalyResult(
                anomalies_detected=False,
                anomaly_indices=[],
                anomaly_points=[],
                severity="none",
                methods_agreed={},
            )

        values = [float(m.get("latency_ms", 0)) for m in metrics]

        z_set = set(zscore_detect(values, self.zscore_threshold))
        iqr_set = set(iqr_detect(values, self.iqr_factor))
        sw_set = set(sliding_window_detect(values, self.window_size))

        # Consensus: flagged by at least 2 of 3 methods
        consensus = (z_set & iqr_set) | (z_set & sw_set) | (iqr_set & sw_set)

        # Also check rows_scanned if available
        if any("rows_scanned" in m for m in metrics):
            scan_vals = [float(m.get("rows_scanned", 0)) for m in metrics]
            scan_z = set(zscore_detect(scan_vals, self.zscore_threshold))
            scan_iqr = set(iqr_detect(scan_vals, self.iqr_factor))
            scan_consensus = scan_z & scan_iqr
            consensus = consensus | scan_consensus

        sorted_consensus = sorted(consensus)
        return AnomalyResult(
            anomalies_detected=len(consensus) > 0,
            anomaly_indices=sorted_consensus,
            anomaly_points=[metrics[i] for i in sorted_consensus],
            severity=classify_severity(values, consensus),
            methods_agreed={
                "zscore": sorted(z_set),
                "iqr": sorted(iqr_set),
                "sliding_window": sorted(sw_set),
            },
        )
