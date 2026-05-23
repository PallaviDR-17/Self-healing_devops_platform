"""
X-DevOps AI Orchestrator
Ties together: Detector → Explainer → Simulator → Decision → Learning
"""

import json
from datetime import datetime
from typing import Optional

from ai_engine.detector.failure_detector import FailureDetector
from ai_engine.explainer.explainability_engine import ExplainabilityEngine
from ai_engine.simulator.simulation_engine import SimulationEngine
from ai_engine.decision.decision_engine import DecisionEngine
from ai_engine.learning.learning_db import LearningDB


class XDevOpsOrchestrator:
    """
    Single entry point for the AI self-healing pipeline.
    Call `process_metrics()` with a metrics snapshot and get back
    the full pipeline result: detection → explanation → simulation → decision.
    """

    def __init__(self, dry_run: bool = True):
        self.detector = FailureDetector()
        self.explainer = ExplainabilityEngine()
        self.simulator = SimulationEngine()
        self.decision = DecisionEngine(dry_run=dry_run)
        self.learning = LearningDB()

    def process_metrics(
        self,
        metrics: dict,
        service_name: str = "app",
        namespace: str = "default",
    ) -> dict:
        """
        Full pipeline: metrics → failure? → explain → simulate → decide → store

        Returns a structured pipeline result. If no failure is detected,
        returns a healthy status.
        """
        # Step 1: Detect
        failure = self.detector.detect_from_metrics(metrics)

        if not failure:
            return {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "metrics": metrics,
                "message": "All metrics within normal thresholds. No action needed.",
            }

        # Step 2: Explain
        explanation = self.explainer.explain(failure)

        # Step 3: Simulate
        simulation = self.simulator.simulate(failure, explanation)

        # Step 4: Decide & Act
        decision = self.decision.decide_and_act(
            simulation,
            service_name=service_name,
            namespace=namespace,
        )

        # Step 5: Store (assume success = decision executed successfully)
        outcome_success = decision.get("status") == "executed" and \
                          (decision.get("execution_result") or {}).get("success", False)

        self.learning.record_incident(
            failure_event=failure,
            decision_record=decision,
            outcome_success=outcome_success,
            notes=f"Auto-healing via orchestrator. dry_run={self.decision.dry_run}",
        )

        return {
            "status": "failure_detected",
            "timestamp": datetime.utcnow().isoformat(),
            "pipeline": {
                "detection": failure,
                "explanation": explanation,
                "simulation": simulation,
                "decision": decision,
            },
            "summary": {
                "primary_metric": failure.get("primary_metric"),
                "severity": failure.get("severity"),
                "root_cause": explanation["root_cause"]["title"],
                "recommended_action": simulation.get("recommended_action_name"),
                "action_status": decision.get("status"),
                "confidence": explanation.get("confidence_pct"),
            },
        }

    def process_logs(
        self,
        log_lines: list[str],
        service_name: str = "app",
        namespace: str = "default",
    ) -> dict:
        """Log-based pipeline variant."""
        failure = self.detector.detect_from_logs(log_lines)

        if not failure:
            return {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "message": "No error patterns found in logs.",
            }

        explanation = self.explainer.explain_from_logs(failure)

        # Build a synthetic failure event for simulation
        synthetic = {**failure, "primary_metric": "error_rate", "raw_metrics": {"error_rate": 10.0}}
        simulation = self.simulator.simulate(synthetic, explanation)
        decision = self.decision.decide_and_act(simulation, service_name=service_name, namespace=namespace)

        return {
            "status": "failure_detected",
            "timestamp": datetime.utcnow().isoformat(),
            "pipeline": {
                "detection": failure,
                "explanation": explanation,
                "simulation": simulation,
                "decision": decision,
            },
        }

    def get_stats(self) -> dict:
        return {
            "learning_summary": self.learning.get_summary(),
            "action_stats": self.learning.get_all_stats(),
            "recent_incidents": self.learning.get_recent_incidents(10),
        }


# ── Demo run ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    orch = XDevOpsOrchestrator(dry_run=True)

    print("=" * 60)
    print("SCENARIO 1: Memory spike + high error rate")
    print("=" * 60)
    result = orch.process_metrics({
        "cpu_usage": 45.0,
        "memory_usage": 92.5,
        "error_rate": 8.3,
        "response_time_ms": 1500,
        "pod_restart_count": 2,
        "disk_usage": 60.0,
    }, service_name="payment-service")
    print(json.dumps(result["summary"], indent=2))

    print("\n" + "=" * 60)
    print("SCENARIO 2: Healthy system")
    print("=" * 60)
    result2 = orch.process_metrics({
        "cpu_usage": 30.0,
        "memory_usage": 55.0,
        "error_rate": 0.5,
        "response_time_ms": 200,
        "pod_restart_count": 0,
        "disk_usage": 40.0,
    })
    print(json.dumps(result2, indent=2))

    print("\n" + "=" * 60)
    print("Learning Stats")
    print("=" * 60)
    print(json.dumps(orch.get_stats()["learning_summary"], indent=2))
