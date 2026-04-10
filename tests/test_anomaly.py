"""Tests for the statistical anomaly detection ensemble."""
import pytest
from src.anomaly.detector import zscore_detect, iqr_detect, sliding_window_detect, AnomalyDetector


# ── Unit tests for individual methods ────────────────────────────────────────

def test_zscore_detects_obvious_spike():
    values = [50.0, 52.0, 48.0, 5000.0, 51.0]
    result = zscore_detect(values)
    assert 3 in result


def test_iqr_detects_obvious_spike():
    values = [50.0, 52.0, 48.0, 5000.0, 51.0]
    result = iqr_detect(values)
    assert 3 in result


def test_sliding_window_detects_spike():
    values = [50.0, 52.0, 48.0, 5000.0, 51.0]
    result = sliding_window_detect(values)
    assert 3 in result


def test_zscore_no_false_positive_flat():
    values = [50.0, 52.0, 49.0, 51.0, 50.0, 48.0, 52.0, 51.0]
    result = zscore_detect(values)
    assert result == []


def test_iqr_no_false_positive_flat():
    values = [50.0, 52.0, 49.0, 51.0, 50.0, 48.0, 52.0, 51.0]
    result = iqr_detect(values)
    assert result == []


# ── AnomalyDetector ensemble tests ───────────────────────────────────────────

def test_detector_finds_spike_at_index_3(anomaly_detector):
    metrics = [
        {"timestamp": f"2025-01-01T0{i}:00:00Z", "latency_ms": 1000 if i != 3 else 50000}
        for i in range(8)
    ]
    result = anomaly_detector.detect(metrics)
    assert result.anomalies_detected is True
    assert 3 in result.anomaly_indices


def test_detector_no_false_positive_on_flat_data(anomaly_detector):
    metrics = [
        {"timestamp": f"2025-01-01T0{i}:00:00Z", "latency_ms": 50 + i}
        for i in range(8)
    ]
    result = anomaly_detector.detect(metrics)
    assert result.anomalies_detected is False


def test_detector_severity_critical_for_50x_spike(anomaly_detector):
    metrics = [
        {"timestamp": f"2025-01-01T0{i}:00:00Z", "latency_ms": 1000 if i != 3 else 50000}
        for i in range(8)
    ]
    result = anomaly_detector.detect(metrics)
    assert result.severity in ("critical", "high")


def test_detector_empty_metrics(anomaly_detector):
    result = anomaly_detector.detect([])
    assert result.anomalies_detected is False
    assert result.anomaly_indices == []


def test_detector_case_010_from_metrics_history(anomaly_detector, metrics_history):
    case10 = next(m for m in metrics_history if m["query_id"] == "case_010")
    result = anomaly_detector.detect(case10["metrics"])
    assert result.anomalies_detected is True


def test_detector_returns_anomaly_result_model(anomaly_detector):
    from src.models import AnomalyResult
    metrics = [{"latency_ms": 100} for _ in range(5)]
    result = anomaly_detector.detect(metrics)
    assert isinstance(result, AnomalyResult)


def test_methods_agreed_dict_structure(anomaly_detector):
    metrics = [
        {"timestamp": f"2025-01-01T0{i}:00:00Z", "latency_ms": 1000 if i != 3 else 50000}
        for i in range(8)
    ]
    result = anomaly_detector.detect(metrics)
    assert "zscore" in result.methods_agreed
    assert "iqr" in result.methods_agreed
    assert "sliding_window" in result.methods_agreed
