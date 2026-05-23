"""
Sample application that exposes Prometheus metrics for X-DevOps to monitor.
Simulates real-world metrics: CPU, memory, error rates, response times.
"""

from flask import Flask, Response, jsonify
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
import random
import threading
import time

app = Flask(__name__)

# ── Prometheus Metrics ────────────────────────────────────────────────────────
request_count = Counter("app_requests_total", "Total HTTP requests", ["method", "endpoint", "status"])
error_count   = Counter("app_errors_total", "Total errors")
response_time = Histogram("app_response_time_seconds", "Response time in seconds")
cpu_gauge     = Gauge("app_cpu_usage_percent", "Simulated CPU usage")
memory_gauge  = Gauge("app_memory_usage_percent", "Simulated memory usage")
error_rate    = Gauge("app_error_rate_percent", "Current error rate percent")
pod_restarts  = Gauge("app_pod_restart_count", "Pod restart count simulation")


def simulate_metrics():
    """Background thread that fluctuates metrics to simulate real-world behavior."""
    restarts = 0
    while True:
        # Normal baseline with occasional spikes
        cpu  = random.uniform(20, 50)
        mem  = random.uniform(40, 65)
        errs = random.uniform(0, 2)

        # 10% chance of a spike scenario
        if random.random() < 0.10:
            spike = random.choice(["memory", "cpu", "errors"])
            if spike == "memory":
                mem = random.uniform(88, 97)
            elif spike == "cpu":
                cpu = random.uniform(87, 99)
            elif spike == "errors":
                errs = random.uniform(10, 35)
                restarts += 1

        cpu_gauge.set(round(cpu, 2))
        memory_gauge.set(round(mem, 2))
        error_rate.set(round(errs, 2))
        pod_restarts.set(restarts)

        time.sleep(5)


# Start background metrics simulation
threading.Thread(target=simulate_metrics, daemon=True).start()


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def home():
    request_count.labels("GET", "/", "200").inc()
    return jsonify({"app": "X-DevOps Sample App", "status": "running"})


@app.route("/api/data")
def data():
    # Simulate occasional slow responses
    delay = random.uniform(0.05, 0.3)
    if random.random() < 0.05:
        delay = random.uniform(1.5, 4.0)
    time.sleep(delay)
    response_time.observe(delay)
    request_count.labels("GET", "/api/data", "200").inc()
    return jsonify({"data": [random.randint(1, 100) for _ in range(10)]})


@app.route("/api/error-prone")
def error_prone():
    if random.random() < 0.3:
        error_count.inc()
        request_count.labels("GET", "/api/error-prone", "500").inc()
        return jsonify({"error": "Internal server error"}), 500
    request_count.labels("GET", "/api/error-prone", "200").inc()
    return jsonify({"result": "ok"})


@app.route("/metrics")
def metrics():
    """Prometheus scrape endpoint."""
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
