"""
Failure Detector Module
Detects anomalies in metrics and logs using rule-based + statistical analysis.
"""

import json
import time
from datetime import datetime
from typing import Optional


class FailureDetector:
    """
    Detects failures from Prometheus metrics and log streams.
    Supports threshold-based and anomaly-based detection.
    """

    THRESHOLDS = {
        "cpu_usage": 85.0,          # percent
        "memory_usage": 90.0,       # percent
        "error_rate": 5.0,          # percent of requests
        "response_time_ms": 2000,   # milliseconds
        "pod_restart_count": 3,     # restarts within window
        "disk_usage": 85.0,         # percent
    }

    SEVERITY_MAP = {
        "cpu_usage": "medium",
        "memory_usage": "high",
        "error_rate": "critical",
        "response_time_ms": "medium",
        "pod_restart_count": "high",
        "disk_usage": "medium",
    }

    def detect_from_metrics(self, metrics: dict) -> Optional[dict]:
        """
        Analyze a metrics snapshot and return a failure event if detected.

        Args:
            metrics: dict with keys matching THRESHOLDS

        Returns:
            Failure event dict or None
        """
        violations = []

        for metric, value in metrics.items():
            threshold = self.THRESHOLDS.get(metric)
            if threshold is not None and value > threshold:
                violations.append({
                    "metric": metric,
                    "value": value,
                    "threshold": threshold,
                    "severity": self.SEVERITY_MAP.get(metric, "medium"),
                    "exceeded_by": round(value - threshold, 2),
                })

        if not violations:
            return None

        # Pick highest severity
        severity_order = {"critical": 3, "high": 2, "medium": 1, "low": 0}
        primary = max(violations, key=lambda v: severity_order.get(v["severity"], 0))

        return {
            "id": f"failure_{int(time.time())}",
            "timestamp": datetime.utcnow().isoformat(),
            "detected": True,
            "primary_metric": primary["metric"],
            "severity": primary["severity"],
            "violations": violations,
            "raw_metrics": metrics,
        }

    def detect_from_logs(self, log_lines: list[str]) -> Optional[dict]:
        """
        Scan log lines for error patterns.
        """
        error_keywords = [
            "OOMKilled", "CrashLoopBackOff", "Error", "Exception",
            "FATAL", "panic", "OutOfMemory", "Timeout", "Connection refused",
            "502", "503", "504", "exit status 1",
        ]

        found_errors = []
        for line in log_lines:
            for kw in error_keywords:
                if kw.lower() in line.lower():
                    found_errors.append({"line": line.strip(), "keyword": kw})
                    break

        if not found_errors:
            return None

        return {
            "id": f"log_failure_{int(time.time())}",
            "timestamp": datetime.utcnow().isoformat(),
            "detected": True,
            "source": "logs",
            "error_count": len(found_errors),
            "errors": found_errors[:10],  # cap at 10 for readability
            "severity": "high" if len(found_errors) > 5 else "medium",
        }


# ── Quick self-test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    detector = FailureDetector()

    sample_metrics = {
        "cpu_usage": 45.0,
        "memory_usage": 92.5,
        "error_rate": 8.3,
        "response_time_ms": 1500,
        "pod_restart_count": 1,
        "disk_usage": 60.0,
    }

    result = detector.detect_from_metrics(sample_metrics)
    print("Metric Detection Result:")
    print(json.dumps(result, indent=2))

    sample_logs = [
        "[2024-01-15 10:23:45] INFO: Request processed",
        "[2024-01-15 10:23:46] ERROR: OOMKilled - container exceeded memory limit",
        "[2024-01-15 10:23:47] FATAL: CrashLoopBackOff detected",
    ]

    log_result = detector.detect_from_logs(sample_logs)
    print("\nLog Detection Result:")
    print(json.dumps(log_result, indent=2))
