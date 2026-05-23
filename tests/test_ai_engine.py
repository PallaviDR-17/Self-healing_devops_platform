"""
Unit tests for X-DevOps AI Engine
Run: pytest tests/ -v
"""

import sys
import os
import pytest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_engine.detector.failure_detector import FailureDetector
from ai_engine.explainer.explainability_engine import ExplainabilityEngine
from ai_engine.simulator.simulation_engine import SimulationEngine
from ai_engine.decision.decision_engine import DecisionEngine
from ai_engine.learning.learning_db import LearningDB
from ai_engine.orchestrator import XDevOpsOrchestrator


# ── Detector Tests ────────────────────────────────────────────────────────────

class TestFailureDetector:

    def setup_method(self):
        self.detector = FailureDetector()

    def test_no_failure_on_healthy_metrics(self):
        metrics = {
            "cpu_usage": 30.0, "memory_usage": 50.0, "error_rate": 0.5,
            "response_time_ms": 300, "pod_restart_count": 0, "disk_usage": 40.0,
        }
        result = self.detector.detect_from_metrics(metrics)
        assert result is None

    def test_detects_memory_failure(self):
        metrics = {
            "cpu_usage": 30.0, "memory_usage": 92.0, "error_rate": 0.5,
            "response_time_ms": 300, "pod_restart_count": 0, "disk_usage": 40.0,
        }
        result = self.detector.detect_from_metrics(metrics)
        assert result is not None
        assert result["detected"] is True
        assert "memory_usage" in [v["metric"] for v in result["violations"]]

    def test_detects_multiple_violations(self):
        metrics = {
            "cpu_usage": 92.0, "memory_usage": 95.0, "error_rate": 12.0,
            "response_time_ms": 300, "pod_restart_count": 0, "disk_usage": 40.0,
        }
        result = self.detector.detect_from_metrics(metrics)
        assert result is not None
        assert len(result["violations"]) >= 3

    def test_detects_critical_severity(self):
        metrics = {
            "cpu_usage": 30.0, "memory_usage": 60.0, "error_rate": 25.0,
            "response_time_ms": 300, "pod_restart_count": 0, "disk_usage": 40.0,
        }
        result = self.detector.detect_from_metrics(metrics)
        assert result["severity"] == "critical"

    def test_log_detection_oom(self):
        logs = [
            "[INFO] Starting service",
            "[ERROR] OOMKilled - container exceeded memory",
            "[FATAL] CrashLoopBackOff",
        ]
        result = self.detector.detect_from_logs(logs)
        assert result is not None
        assert result["detected"] is True
        assert result["error_count"] >= 2

    def test_log_detection_no_errors(self):
        logs = ["[INFO] Request processed", "[DEBUG] Cache hit", "[INFO] Health check OK"]
        result = self.detector.detect_from_logs(logs)
        assert result is None


# ── Explainer Tests ───────────────────────────────────────────────────────────

class TestExplainabilityEngine:

    def setup_method(self):
        self.detector = FailureDetector()
        self.explainer = ExplainabilityEngine()

    def _get_failure(self, metrics):
        return self.detector.detect_from_metrics(metrics)

    def test_explanation_has_required_fields(self):
        failure = self._get_failure({
            "cpu_usage": 30.0, "memory_usage": 92.0, "error_rate": 0.5,
            "response_time_ms": 300, "pod_restart_count": 0, "disk_usage": 40.0,
        })
        exp = self.explainer.explain(failure)
        assert "summary" in exp
        assert "root_cause" in exp
        assert "confidence" in exp
        assert "recommendation" in exp

    def test_confidence_is_between_0_and_1(self):
        failure = self._get_failure({
            "cpu_usage": 30.0, "memory_usage": 92.0, "error_rate": 0.5,
            "response_time_ms": 300, "pod_restart_count": 0, "disk_usage": 40.0,
        })
        exp = self.explainer.explain(failure)
        assert 0.0 <= exp["confidence"] <= 1.0

    def test_critical_severity_has_high_confidence(self):
        failure = self._get_failure({
            "cpu_usage": 30.0, "memory_usage": 60.0, "error_rate": 25.0,
            "response_time_ms": 300, "pod_restart_count": 0, "disk_usage": 40.0,
        })
        exp = self.explainer.explain(failure)
        assert exp["confidence"] >= 0.90


# ── Simulator Tests ───────────────────────────────────────────────────────────

class TestSimulationEngine:

    def setup_method(self):
        self.simulator = SimulationEngine()

    def _fake_failure(self, metric="memory_usage", severity="high"):
        return {
            "id": "test_001",
            "timestamp": "2024-01-01T00:00:00",
            "primary_metric": metric,
            "severity": severity,
            "raw_metrics": {
                "cpu_usage": 45.0, "memory_usage": 92.5, "error_rate": 8.3,
                "response_time_ms": 1500, "pod_restart_count": 2, "disk_usage": 60.0,
            },
        }

    def test_returns_multiple_simulations(self):
        result = self.simulator.simulate(self._fake_failure(), {})
        assert len(result["simulations"]) >= 2

    def test_recommended_action_is_highest_scored(self):
        result = self.simulator.simulate(self._fake_failure(), {})
        top_score = result["simulations"][0]["score"]
        rec_action = result["recommended_action"]
        top_action = result["simulations"][0]["action_key"]
        assert rec_action == top_action

    def test_rollback_preferred_for_error_rate(self):
        result = self.simulator.simulate(self._fake_failure("error_rate", "critical"), {})
        assert result["recommended_action"] == "rollback_deployment"

    def test_scale_preferred_for_cpu(self):
        result = self.simulator.simulate(self._fake_failure("cpu_usage", "high"), {})
        assert result["recommended_action"] == "scale_pods"


# ── Decision Engine Tests ─────────────────────────────────────────────────────

class TestDecisionEngine:

    def setup_method(self):
        self.engine = DecisionEngine(dry_run=True)

    def _fake_sim(self, action="scale_pods", confidence=0.85):
        return {
            "failure_id": "test_001",
            "primary_metric": "memory_usage",
            "severity": "high",
            "recommended_action": action,
            "recommended_action_name": action.replace("_", " ").title(),
            "simulation_confidence": confidence,
            "simulations": [{
                "action_key": action, "name": action, "success_probability": confidence,
                "estimated_downtime_sec": 0, "risk": "low", "score": confidence,
            }],
        }

    def test_dry_run_executes_successfully(self):
        result = self.engine.decide_and_act(self._fake_sim())
        assert result["status"] == "executed"
        assert result["dry_run"] is True

    def test_skips_on_low_confidence(self):
        result = self.engine.decide_and_act(self._fake_sim(confidence=0.40))
        assert result["status"] == "skipped"
        assert "Confidence" in result["skip_reason"]

    def test_command_contains_service_name(self):
        result = self.engine.decide_and_act(self._fake_sim(), service_name="payment-svc")
        assert "payment-svc" in result["command"]


# ── Learning DB Tests ─────────────────────────────────────────────────────────

class TestLearningDB:

    def setup_method(self):
        self.db = LearningDB(db_path=Path("/tmp/test_xdevops_learning.db"))

    def test_record_and_retrieve_incident(self):
        failure = {
            "id": "test_f_001", "timestamp": "2024-01-01T00:00:00",
            "primary_metric": "memory_usage", "severity": "high",
            "raw_metrics": {"memory_usage": 92.0},
        }
        decision = {"action_taken": "scale_pods", "confidence": 0.85}
        row_id = self.db.record_incident(failure, decision, outcome_success=True)
        assert row_id > 0

    def test_success_rate_calculation(self):
        failure = {
            "id": "test_sr_001", "timestamp": "2024-01-01T00:00:00",
            "primary_metric": "cpu_usage", "severity": "high", "raw_metrics": {},
        }
        dec = {"action_taken": "restart_service", "confidence": 0.72}
        self.db.record_incident(failure, dec, True)
        self.db.record_incident(failure, dec, True)
        self.db.record_incident(failure, dec, False)
        rate = self.db.get_success_rate("restart_service", "cpu_usage")
        assert rate is not None

    def test_summary_returns_correct_counts(self):
        summary = self.db.get_summary()
        assert "total_incidents" in summary
        assert "resolved" in summary
        assert "resolution_rate" in summary


# ── Orchestrator Integration Test ─────────────────────────────────────────────

class TestOrchestrator:

    def setup_method(self):
        self.orch = XDevOpsOrchestrator(dry_run=True)
        # Override learning DB to use temp file
        self.orch.learning = LearningDB(db_path=Path("/tmp/test_orch_learning.db"))

    def test_healthy_metrics_returns_healthy(self):
        result = self.orch.process_metrics({
            "cpu_usage": 20.0, "memory_usage": 40.0, "error_rate": 0.1,
            "response_time_ms": 100, "pod_restart_count": 0, "disk_usage": 30.0,
        })
        assert result["status"] == "healthy"

    def test_failure_metrics_runs_full_pipeline(self):
        result = self.orch.process_metrics({
            "cpu_usage": 40.0, "memory_usage": 95.0, "error_rate": 20.0,
            "response_time_ms": 3000, "pod_restart_count": 5, "disk_usage": 60.0,
        })
        assert result["status"] == "failure_detected"
        assert "pipeline" in result
        assert "detection" in result["pipeline"]
        assert "explanation" in result["pipeline"]
        assert "simulation" in result["pipeline"]
        assert "decision" in result["pipeline"]

    def test_pipeline_summary_contains_expected_keys(self):
        result = self.orch.process_metrics({
            "cpu_usage": 40.0, "memory_usage": 95.0, "error_rate": 20.0,
            "response_time_ms": 3000, "pod_restart_count": 5, "disk_usage": 60.0,
        })
        if result["status"] == "failure_detected":
            summary = result["summary"]
            assert "primary_metric" in summary
            assert "severity" in summary
            assert "root_cause" in summary
            assert "recommended_action" in summary
