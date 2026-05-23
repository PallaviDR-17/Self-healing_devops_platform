"""
Simulation Engine
Virtually simulates possible remediation actions and scores each one
before committing to any real infrastructure change.
"""

import random
import json
from typing import Optional


class SimulationEngine:
    """
    Simulates the outcome of remediation actions (restart, scale, rollback)
    using heuristic scoring and historical success rates.
    Returns ranked list of actions with predicted outcomes.
    """

    # Maps primary failure metric → preferred action ordering
    ACTION_PREFERENCE = {
        "memory_usage":     ["scale_pods", "restart_service", "rollback_deployment"],
        "cpu_usage":        ["scale_pods", "restart_service", "rollback_deployment"],
        "error_rate":       ["rollback_deployment", "restart_service", "scale_pods"],
        "response_time_ms": ["scale_pods", "restart_service", "rollback_deployment"],
        "pod_restart_count":["restart_service", "rollback_deployment", "scale_pods"],
        "disk_usage":       ["cleanup_logs", "restart_service", "scale_pods"],
    }

    # Base success probability per action (tunable from learning DB)
    BASE_SUCCESS_RATES = {
        "restart_service":      0.72,
        "scale_pods":           0.85,
        "rollback_deployment":  0.90,
        "cleanup_logs":         0.95,
    }

    ACTION_DESCRIPTIONS = {
        "restart_service": {
            "name": "Restart Service",
            "description": "Gracefully restart the affected pods, clearing in-memory state.",
            "estimated_downtime_sec": 30,
            "risk": "low",
            "kubernetes_command": "kubectl rollout restart deployment/{service_name} -n {namespace}",
        },
        "scale_pods": {
            "name": "Scale Pods",
            "description": "Increase the number of running pod replicas to distribute load.",
            "estimated_downtime_sec": 0,
            "risk": "low",
            "kubernetes_command": "kubectl scale deployment/{service_name} --replicas={new_replicas} -n {namespace}",
        },
        "rollback_deployment": {
            "name": "Rollback Deployment",
            "description": "Revert to the last known stable deployment version.",
            "estimated_downtime_sec": 60,
            "risk": "medium",
            "kubernetes_command": "kubectl rollout undo deployment/{service_name} -n {namespace}",
        },
        "cleanup_logs": {
            "name": "Cleanup Logs",
            "description": "Remove old log files and rotate active logs to free disk space.",
            "estimated_downtime_sec": 0,
            "risk": "none",
            "kubernetes_command": "kubectl exec {pod_name} -- find /var/log -mtime +7 -delete",
        },
    }

    def simulate(self, failure_event: dict, explanation: dict) -> dict:
        """
        Run simulations for all candidate actions and return ranked results.

        Args:
            failure_event: From FailureDetector
            explanation:   From ExplainabilityEngine

        Returns:
            dict with ranked simulations and recommended action
        """
        primary_metric = failure_event.get("primary_metric", "error_rate")
        severity = failure_event.get("severity", "medium")
        raw_metrics = failure_event.get("raw_metrics", {})

        actions = self.ACTION_PREFERENCE.get(
            primary_metric,
            ["restart_service", "scale_pods", "rollback_deployment"]
        )

        simulations = []
        for action in actions:
            sim = self._simulate_action(action, primary_metric, severity, raw_metrics)
            simulations.append(sim)

        # Sort by score descending
        simulations.sort(key=lambda x: x["score"], reverse=True)

        return {
            "failure_id": failure_event.get("id"),
            "primary_metric": primary_metric,
            "severity": severity,
            "simulations": simulations,
            "recommended_action": simulations[0]["action_key"],
            "recommended_action_name": simulations[0]["name"],
            "simulation_confidence": simulations[0]["success_probability"],
        }

    def _simulate_action(
        self,
        action_key: str,
        primary_metric: str,
        severity: str,
        raw_metrics: dict,
    ) -> dict:
        """Simulate a single remediation action."""
        template = self.ACTION_DESCRIPTIONS.get(action_key, {})
        base_rate = self.BASE_SUCCESS_RATES.get(action_key, 0.70)

        # Adjust probability based on severity
        severity_penalty = {"critical": -0.10, "high": -0.05, "medium": 0.0, "low": 0.05}
        adjusted_rate = min(0.99, max(0.30, base_rate + severity_penalty.get(severity, 0)))

        # Simulate predicted metric improvement
        predicted_metrics = self._predict_post_action_metrics(action_key, raw_metrics)

        # Score = success_probability * (1 - risk_factor) * (1 if no downtime else 0.9)
        risk_penalty = {"none": 0, "low": 0.05, "medium": 0.15, "high": 0.30}
        risk = template.get("risk", "low")
        downtime = template.get("estimated_downtime_sec", 0)
        downtime_factor = 0.95 if downtime > 0 else 1.0

        score = round(
            adjusted_rate * (1 - risk_penalty.get(risk, 0.05)) * downtime_factor,
            4,
        )

        return {
            "action_key": action_key,
            "name": template.get("name", action_key),
            "description": template.get("description", ""),
            "success_probability": round(adjusted_rate, 2),
            "success_probability_pct": f"{int(adjusted_rate * 100)}%",
            "estimated_downtime_sec": downtime,
            "risk": risk,
            "score": score,
            "kubernetes_command": template.get("kubernetes_command", ""),
            "predicted_metrics_after": predicted_metrics,
            "simulation_status": "passed",
        }

    def _predict_post_action_metrics(self, action: str, metrics: dict) -> dict:
        """Heuristic prediction of metrics after applying an action."""
        m = dict(metrics)

        if action == "scale_pods":
            m["cpu_usage"] = round(m.get("cpu_usage", 50) * 0.55, 1)
            m["memory_usage"] = round(m.get("memory_usage", 70) * 0.60, 1)
            m["response_time_ms"] = round(m.get("response_time_ms", 500) * 0.50, 0)

        elif action == "restart_service":
            m["memory_usage"] = round(m.get("memory_usage", 70) * 0.65, 1)
            m["pod_restart_count"] = 0
            m["error_rate"] = round(m.get("error_rate", 2) * 0.40, 1)

        elif action == "rollback_deployment":
            m["error_rate"] = round(m.get("error_rate", 2) * 0.10, 1)
            m["response_time_ms"] = round(m.get("response_time_ms", 500) * 0.60, 0)
            m["pod_restart_count"] = 0

        elif action == "cleanup_logs":
            m["disk_usage"] = round(m.get("disk_usage", 80) * 0.55, 1)

        return m


# ── Quick self-test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    engine = SimulationEngine()

    fake_failure = {
        "id": "failure_1234",
        "timestamp": "2024-01-15T10:23:45",
        "primary_metric": "memory_usage",
        "severity": "high",
        "raw_metrics": {
            "cpu_usage": 45.0,
            "memory_usage": 92.5,
            "error_rate": 8.3,
            "response_time_ms": 1500,
            "pod_restart_count": 2,
            "disk_usage": 60.0,
        },
    }

    result = engine.simulate(fake_failure, {})
    print(json.dumps(result, indent=2))
