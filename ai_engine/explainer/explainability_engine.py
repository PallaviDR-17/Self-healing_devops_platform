"""
Explainability Module
Generates human-readable explanations for detected failures with confidence scores.
"""

import json
from typing import Optional


class ExplainabilityEngine:
    """
    Converts raw failure events into structured, human-readable explanations.
    Provides root-cause analysis with contributing factors and confidence score.
    """

    EXPLANATIONS = {
        "memory_usage": {
            "title": "High Memory Usage",
            "root_cause": "The application is consuming excessive memory, likely due to a memory leak, "
                          "increased traffic load, or misconfigured JVM/heap settings.",
            "impact": "Pod crash (OOMKilled), service unavailability, cascading failures.",
            "indicators": ["memory_usage > 90%", "OOMKilled in logs", "pod restarts increasing"],
        },
        "cpu_usage": {
            "title": "High CPU Utilization",
            "root_cause": "CPU is saturated, possibly due to an infinite loop, heavy computation, "
                          "insufficient pod replicas, or a traffic surge.",
            "impact": "Slow response times, request timeouts, degraded user experience.",
            "indicators": ["cpu_usage > 85%", "high response latency", "throttling events"],
        },
        "error_rate": {
            "title": "Elevated Error Rate",
            "root_cause": "A significant percentage of requests are failing. This may indicate a "
                          "bad deployment, downstream service failure, or database connectivity issues.",
            "impact": "Users experiencing errors, SLA violations, potential data loss.",
            "indicators": ["error_rate > 5%", "5xx HTTP errors", "exception stack traces in logs"],
        },
        "response_time_ms": {
            "title": "High Response Latency",
            "root_cause": "Requests are taking too long. Causes include slow database queries, "
                          "network congestion, or resource contention.",
            "impact": "Poor user experience, timeout errors, SLA breaches.",
            "indicators": ["response_time > 2000ms", "slow query logs", "queue buildup"],
        },
        "pod_restart_count": {
            "title": "Pod CrashLoop Detected",
            "root_cause": "The pod is repeatedly crashing and restarting. "
                          "Common causes: application startup failure, missing config/secrets, "
                          "or persistent OOMKill.",
            "impact": "Service intermittently unavailable, data inconsistency risk.",
            "indicators": ["CrashLoopBackOff", "restart count > 3", "exit code non-zero"],
        },
        "disk_usage": {
            "title": "High Disk Usage",
            "root_cause": "Storage is nearly full. Log accumulation, large temp files, "
                          "or missing log rotation policies are common causes.",
            "impact": "Application write failures, database corruption, pod eviction.",
            "indicators": ["disk_usage > 85%", "no space left on device errors"],
        },
    }

    CONFIDENCE_RULES = {
        "critical": 0.95,
        "high": 0.85,
        "medium": 0.70,
        "low": 0.55,
    }

    def explain(self, failure_event: dict) -> dict:
        """
        Generate a full explanation for a failure event.

        Args:
            failure_event: Output from FailureDetector.detect_from_metrics()

        Returns:
            Structured explanation dict
        """
        primary_metric = failure_event.get("primary_metric", "unknown")
        severity = failure_event.get("severity", "medium")
        violations = failure_event.get("violations", [])
        raw_metrics = failure_event.get("raw_metrics", {})

        template = self.EXPLANATIONS.get(primary_metric, {
            "title": "Unknown Failure",
            "root_cause": "An anomaly was detected but the specific cause could not be determined.",
            "impact": "System may be degraded.",
            "indicators": [],
        })

        confidence = self.CONFIDENCE_RULES.get(severity, 0.70)

        # Build contributing factors from all violations
        contributing_factors = []
        for v in violations:
            factor_template = self.EXPLANATIONS.get(v["metric"], {})
            if factor_template:
                contributing_factors.append({
                    "metric": v["metric"],
                    "title": factor_template.get("title", v["metric"]),
                    "value": v["value"],
                    "threshold": v["threshold"],
                    "exceeded_by": v["exceeded_by"],
                })

        # Generate one-liner summary
        primary_value = raw_metrics.get(primary_metric, "N/A")
        threshold = self.EXPLANATIONS.get(primary_metric, {})
        summary = (
            f"{template['title']} detected: {primary_metric.replace('_', ' ')} "
            f"is at {primary_value} (threshold: "
            f"{self.get_threshold_str(primary_metric)}), causing {severity}-severity incident."
        )

        return {
            "failure_id": failure_event.get("id"),
            "timestamp": failure_event.get("timestamp"),
            "summary": summary,
            "severity": severity,
            "confidence": confidence,
            "confidence_pct": f"{int(confidence * 100)}%",
            "root_cause": {
                "title": template["title"],
                "description": template["root_cause"],
                "impact": template["impact"],
                "indicators": template["indicators"],
            },
            "contributing_factors": contributing_factors,
            "recommendation": self._recommend(primary_metric, severity),
        }

    def explain_from_logs(self, log_failure: dict) -> dict:
        """Generate explanation from a log-based failure event."""
        errors = log_failure.get("errors", [])
        keywords = list({e["keyword"] for e in errors})

        cause = "Application errors detected in logs."
        if "OOMKilled" in keywords:
            cause = "Container was killed due to out-of-memory condition."
        elif "CrashLoopBackOff" in keywords:
            cause = "Pod is in a crash loop — repeatedly failing to start."
        elif any(k in keywords for k in ["502", "503", "504"]):
            cause = "Upstream service returning HTTP errors, suggesting dependency failure."
        elif "Connection refused" in keywords:
            cause = "Service cannot connect to a dependency (DB, cache, or API)."

        return {
            "failure_id": log_failure.get("id"),
            "timestamp": log_failure.get("timestamp"),
            "summary": f"Log analysis found {log_failure.get('error_count', 0)} error(s): {', '.join(keywords[:3])}",
            "severity": log_failure.get("severity"),
            "confidence": 0.80,
            "confidence_pct": "80%",
            "root_cause": {
                "title": "Log-Based Error Detection",
                "description": cause,
                "impact": "Service degradation or complete unavailability.",
                "indicators": keywords,
            },
            "contributing_factors": [],
            "recommendation": "Investigate pod logs, check recent deployments, and verify downstream dependencies.",
        }

    def get_threshold_str(self, metric: str) -> str:
        from ai_engine.detector.failure_detector import FailureDetector
        t = FailureDetector.THRESHOLDS.get(metric)
        return str(t) if t else "N/A"

    def _recommend(self, metric: str, severity: str) -> str:
        recs = {
            "memory_usage": "Scale horizontally (add pods) or investigate memory leak. Consider increasing pod memory limits.",
            "cpu_usage": "Scale pods horizontally or vertically. Profile application for CPU-intensive operations.",
            "error_rate": "Rollback to last stable deployment. Check downstream service health and database connectivity.",
            "response_time_ms": "Check database query performance, enable caching, and review network latency.",
            "pod_restart_count": "Inspect pod logs for startup errors. Verify all ConfigMaps and Secrets are mounted correctly.",
            "disk_usage": "Clean up old logs and temp files. Implement log rotation. Consider expanding PVC.",
        }
        return recs.get(metric, "Investigate metrics, logs, and recent changes to identify the root cause.")


# ── Quick self-test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

    from ai_engine.detector.failure_detector import FailureDetector

    detector = FailureDetector()
    explainer = ExplainabilityEngine()

    metrics = {
        "cpu_usage": 45.0,
        "memory_usage": 92.5,
        "error_rate": 8.3,
        "response_time_ms": 1500,
        "pod_restart_count": 1,
        "disk_usage": 60.0,
    }

    failure = detector.detect_from_metrics(metrics)
    if failure:
        explanation = explainer.explain(failure)
        print(json.dumps(explanation, indent=2))
