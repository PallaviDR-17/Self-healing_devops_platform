"""
Decision Engine
Selects the best remediation action from simulation results and executes it
(or mocks execution in dry-run mode).
"""

import json
import time
import subprocess
from datetime import datetime
from typing import Optional


class DecisionEngine:
    """
    Takes simulation results and:
    1. Selects the best action
    2. Validates constraints (cooldown, severity threshold)
    3. Executes (or dry-runs) the Kubernetes remediation command
    4. Returns an action record for the Learning DB
    """

    # Don't auto-execute for low-confidence or low-severity events
    AUTO_EXECUTE_THRESHOLD = 0.65
    COOLDOWN_SECONDS = 120  # Don't re-trigger same action within 2 min

    def __init__(self, dry_run: bool = True):
        """
        Args:
            dry_run: If True, commands are logged but NOT actually run.
                     Set to False in production with kubectl access.
        """
        self.dry_run = dry_run
        self._last_action_time: dict[str, float] = {}

    def decide_and_act(
        self,
        simulation_result: dict,
        service_name: str = "app",
        namespace: str = "default",
        new_replicas: int = 5,
    ) -> dict:
        """
        Main entry point — decide which action to take and execute it.

        Returns:
            Action record dict (stored in Learning DB)
        """
        recommended = simulation_result.get("recommended_action")
        confidence = simulation_result.get("simulation_confidence", 0)
        simulations = simulation_result.get("simulations", [])

        # Find full simulation detail for recommended action
        chosen_sim = next(
            (s for s in simulations if s["action_key"] == recommended), {}
        )

        # Cooldown check
        last_time = self._last_action_time.get(recommended, 0)
        if time.time() - last_time < self.COOLDOWN_SECONDS:
            return self._skip_record(
                simulation_result,
                reason=f"Cooldown active for '{recommended}' ({self.COOLDOWN_SECONDS}s)",
            )

        # Confidence check
        if confidence < self.AUTO_EXECUTE_THRESHOLD:
            return self._skip_record(
                simulation_result,
                reason=f"Confidence {confidence:.0%} below threshold {self.AUTO_EXECUTE_THRESHOLD:.0%}",
            )

        # Build command
        command = self._build_command(
            recommended, service_name, namespace, new_replicas
        )

        # Execute
        execution_result = self._execute(command)
        self._last_action_time[recommended] = time.time()

        return {
            "decision_id": f"dec_{int(time.time())}",
            "timestamp": datetime.utcnow().isoformat(),
            "failure_id": simulation_result.get("failure_id"),
            "action_taken": recommended,
            "action_name": chosen_sim.get("name", recommended),
            "command": command,
            "dry_run": self.dry_run,
            "confidence": confidence,
            "execution_result": execution_result,
            "status": "executed" if execution_result.get("success") else "failed",
            "service_name": service_name,
            "namespace": namespace,
        }

    def _build_command(
        self,
        action: str,
        service: str,
        namespace: str,
        replicas: int,
    ) -> str:
        templates = {
            "restart_service":
                f"kubectl rollout restart deployment/{service} -n {namespace}",
            "scale_pods":
                f"kubectl scale deployment/{service} --replicas={replicas} -n {namespace}",
            "rollback_deployment":
                f"kubectl rollout undo deployment/{service} -n {namespace}",
            "cleanup_logs":
                f"kubectl exec -n {namespace} $(kubectl get pod -n {namespace} -l app={service} "
                f"-o jsonpath='{{.items[0].metadata.name}}') -- find /var/log -mtime +7 -delete",
        }
        return templates.get(action, f"echo 'Unknown action: {action}'")

    def _execute(self, command: str) -> dict:
        """Execute or dry-run the command."""
        if self.dry_run:
            return {
                "success": True,
                "stdout": f"[DRY RUN] Would execute: {command}",
                "stderr": "",
                "return_code": 0,
            }

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "return_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "stdout": "", "stderr": "Command timed out", "return_code": -1}
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e), "return_code": -1}

    def _skip_record(self, simulation_result: dict, reason: str) -> dict:
        return {
            "decision_id": f"dec_{int(time.time())}",
            "timestamp": datetime.utcnow().isoformat(),
            "failure_id": simulation_result.get("failure_id"),
            "action_taken": None,
            "status": "skipped",
            "skip_reason": reason,
            "dry_run": self.dry_run,
        }


# ── Quick self-test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    engine = DecisionEngine(dry_run=True)

    fake_simulation = {
        "failure_id": "failure_1234",
        "primary_metric": "memory_usage",
        "severity": "high",
        "recommended_action": "scale_pods",
        "recommended_action_name": "Scale Pods",
        "simulation_confidence": 0.85,
        "simulations": [
            {
                "action_key": "scale_pods",
                "name": "Scale Pods",
                "success_probability": 0.85,
                "estimated_downtime_sec": 0,
                "risk": "low",
                "score": 0.80,
            }
        ],
    }

    result = engine.decide_and_act(fake_simulation, service_name="myapp")
    print(json.dumps(result, indent=2))
