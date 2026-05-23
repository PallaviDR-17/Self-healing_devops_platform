"""
X-DevOps Backend API
FastAPI application exposing AI engine capabilities via REST.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import sys
import os

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ai_engine.orchestrator import XDevOpsOrchestrator

app = FastAPI(
    title="X-DevOps AI Engine API",
    description="Explainable AI-Driven Self-Healing DevOps Platform",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Singleton orchestrator (dry_run=True by default — safe for demo)
orchestrator = XDevOpsOrchestrator(dry_run=True)


# ── Request / Response Models ─────────────────────────────────────────────────

class MetricsPayload(BaseModel):
    cpu_usage: float = 30.0
    memory_usage: float = 55.0
    error_rate: float = 0.5
    response_time_ms: float = 200.0
    pod_restart_count: float = 0.0
    disk_usage: float = 40.0
    service_name: str = "app"
    namespace: str = "default"


class LogPayload(BaseModel):
    log_lines: list[str]
    service_name: str = "app"
    namespace: str = "default"


class ChatQuery(BaseModel):
    question: str
    context: Optional[dict] = None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    return {"message": "X-DevOps AI Engine is running 🚀", "version": "1.0.0"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}


@app.post("/api/analyze/metrics", tags=["AI Engine"])
def analyze_metrics(payload: MetricsPayload):
    """
    Run the full AI pipeline on a metrics snapshot.
    Returns: detection, explanation, simulation, decision results.
    """
    metrics = payload.dict(exclude={"service_name", "namespace"})
    result = orchestrator.process_metrics(
        metrics,
        service_name=payload.service_name,
        namespace=payload.namespace,
    )
    return result


@app.post("/api/analyze/logs", tags=["AI Engine"])
def analyze_logs(payload: LogPayload):
    """Analyze log lines for errors and run self-healing pipeline."""
    result = orchestrator.process_logs(
        payload.log_lines,
        service_name=payload.service_name,
        namespace=payload.namespace,
    )
    return result


@app.get("/api/stats", tags=["Learning"])
def get_stats():
    """Return learning database statistics and recent incidents."""
    return orchestrator.get_stats()


@app.post("/api/chat", tags=["ChatOps"])
def chat(query: ChatQuery):
    """
    Simple ChatOps endpoint — answers questions about system status.
    Powered by pattern matching (extend with LLM integration optionally).
    """
    q = query.question.lower()
    stats = orchestrator.get_stats()
    summary = stats.get("learning_summary", {})

    if any(w in q for w in ["why", "cause", "failed", "crash", "restart"]):
        recent = stats.get("recent_incidents", [])
        if recent:
            last = recent[0]
            return {
                "answer": (
                    f"The last incident involved '{last.get('primary_metric')}' at "
                    f"{last.get('severity')} severity. "
                    f"Action taken: {last.get('action_taken')}. "
                    f"Result: {'Success ✅' if last.get('success') else 'Failed ❌'}."
                ),
                "incident": last,
            }
        return {"answer": "No recent incidents recorded in the learning database."}

    if any(w in q for w in ["status", "healthy", "health", "how"]):
        return {
            "answer": (
                f"System has handled {summary.get('total_incidents', 0)} total incidents. "
                f"Resolution rate: {summary.get('resolution_rate', 0):.0%}. "
                f"Currently monitoring all services."
            )
        }

    if any(w in q for w in ["action", "fix", "solution", "best"]):
        action_stats = stats.get("action_stats", [])
        if action_stats:
            best = action_stats[0]
            return {
                "answer": (
                    f"The most effective action historically is '{best['action']}' "
                    f"with a {best['success_rate']:.0%} success rate over {best['total']} incidents."
                )
            }

    return {
        "answer": "I can answer questions about system failures, status, and best remediation actions. Try asking 'Why did the system restart?' or 'What is the system status?'"
    }


@app.post("/api/simulate/demo", tags=["Demo"])
def demo_failure(scenario: str = "memory"):
    """
    Trigger a pre-built demo scenario for showcasing.
    Scenarios: memory | cpu | error_rate | rollback | healthy
    """
    scenarios = {
        "memory": {
            "cpu_usage": 40.0, "memory_usage": 93.0, "error_rate": 2.0,
            "response_time_ms": 800, "pod_restart_count": 1, "disk_usage": 55.0,
        },
        "cpu": {
            "cpu_usage": 94.0, "memory_usage": 65.0, "error_rate": 3.0,
            "response_time_ms": 3500, "pod_restart_count": 0, "disk_usage": 50.0,
        },
        "error_rate": {
            "cpu_usage": 50.0, "memory_usage": 60.0, "error_rate": 22.0,
            "response_time_ms": 900, "pod_restart_count": 4, "disk_usage": 48.0,
        },
        "rollback": {
            "cpu_usage": 55.0, "memory_usage": 70.0, "error_rate": 35.0,
            "response_time_ms": 5000, "pod_restart_count": 5, "disk_usage": 60.0,
        },
        "healthy": {
            "cpu_usage": 25.0, "memory_usage": 45.0, "error_rate": 0.2,
            "response_time_ms": 150, "pod_restart_count": 0, "disk_usage": 35.0,
        },
    }

    metrics = scenarios.get(scenario)
    if not metrics:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {scenario}. Use: {list(scenarios.keys())}")

    result = orchestrator.process_metrics(metrics, service_name=f"demo-{scenario}-service")
    return result
