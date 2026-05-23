"""
Crash Simulator CLI
Sends pre-built crash scenarios to the X-DevOps backend API for demo purposes.
Usage: python scripts/crash_simulator.py [scenario]
"""

import sys
import json
import urllib.request
import urllib.error
import time

API_BASE = "http://localhost:8000"

SCENARIOS = {
    "memory": {
        "name": "Memory Spike (OOMKill simulation)",
        "metrics": {
            "cpu_usage": 40.0, "memory_usage": 93.5, "error_rate": 2.1,
            "response_time_ms": 800, "pod_restart_count": 2, "disk_usage": 55.0,
            "service_name": "payment-service", "namespace": "production"
        }
    },
    "cpu": {
        "name": "CPU Saturation (traffic surge)",
        "metrics": {
            "cpu_usage": 95.0, "memory_usage": 65.0, "error_rate": 3.5,
            "response_time_ms": 4200, "pod_restart_count": 0, "disk_usage": 50.0,
            "service_name": "api-gateway", "namespace": "production"
        }
    },
    "error_rate": {
        "name": "High Error Rate (bad deployment)",
        "metrics": {
            "cpu_usage": 50.0, "memory_usage": 60.0, "error_rate": 28.0,
            "response_time_ms": 900, "pod_restart_count": 5, "disk_usage": 48.0,
            "service_name": "checkout-service", "namespace": "production"
        }
    },
    "rollback": {
        "name": "Cascading Failure (rollback needed)",
        "metrics": {
            "cpu_usage": 55.0, "memory_usage": 72.0, "error_rate": 42.0,
            "response_time_ms": 6000, "pod_restart_count": 8, "disk_usage": 60.0,
            "service_name": "order-service", "namespace": "production"
        }
    },
    "healthy": {
        "name": "Healthy System (no action needed)",
        "metrics": {
            "cpu_usage": 22.0, "memory_usage": 44.0, "error_rate": 0.2,
            "response_time_ms": 140, "pod_restart_count": 0, "disk_usage": 33.0,
            "service_name": "user-service", "namespace": "production"
        }
    },
}


def call_api(path, data):
    url = f"{API_BASE}{path}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        print(f"\n❌ Cannot reach backend at {API_BASE}")
        print("   Start it first with:")
        print("   cd backend && uvicorn main:app --reload\n")
        sys.exit(1)


def run_scenario(name):
    scenario = SCENARIOS.get(name)
    if not scenario:
        print(f"Unknown scenario '{name}'. Available: {', '.join(SCENARIOS.keys())}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"🎭 SCENARIO: {scenario['name']}")
    print(f"{'='*60}")
    print("📤 Sending metrics to AI engine...")

    result = call_api("/api/analyze/metrics", scenario["metrics"])

    status = result.get("status")

    if status == "healthy":
        print("\n✅ RESULT: System is HEALTHY — no action needed.")
        print(f"   Message: {result.get('message')}")
        return

    summary = result.get("summary", {})
    pipeline = result.get("pipeline", {})

    print(f"\n🔴 FAILURE DETECTED")
    print(f"   Metric    : {summary.get('primary_metric')}")
    print(f"   Severity  : {summary.get('severity', '').upper()}")
    print(f"   Confidence: {summary.get('confidence')}")

    print(f"\n🧠 ROOT CAUSE")
    print(f"   {summary.get('root_cause')}")

    exp = pipeline.get("explanation", {})
    print(f"   {exp.get('root_cause', {}).get('description', '')}")

    print(f"\n🎭 SIMULATIONS")
    for sim in pipeline.get("simulation", {}).get("simulations", []):
        star = "⭐" if sim["action_key"] == pipeline.get("simulation", {}).get("recommended_action") else "  "
        print(f"   {star} {sim['name']:25s} | Score: {sim['score']:.2f} | Success: {sim['success_probability_pct']} | Risk: {sim['risk']}")

    decision = pipeline.get("decision", {})
    print(f"\n⚡ DECISION")
    print(f"   Action : {decision.get('action_name')}")
    print(f"   Status : {decision.get('status', '').upper()}")
    print(f"   Command: {decision.get('command')}")
    if decision.get("dry_run"):
        print("   ⚠️  DRY RUN — set DRY_RUN=false in .env to execute on real cluster")

    rec = exp.get("recommendation", "")
    if rec:
        print(f"\n💊 RECOMMENDATION")
        print(f"   {rec}")

    print(f"\n📚 Incident stored in learning database.\n")


def run_all():
    for name in SCENARIOS:
        run_scenario(name)
        time.sleep(1)


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "help":
        print("\nX-DevOps Crash Simulator")
        print("Usage: python scripts/crash_simulator.py <scenario>")
        print("\nAvailable scenarios:")
        for k, v in SCENARIOS.items():
            print(f"  {k:15s} — {v['name']}")
        print("  all            — run all scenarios sequentially")
        sys.exit(0)

    arg = sys.argv[1]
    if arg == "all":
        run_all()
    else:
        run_scenario(arg)
