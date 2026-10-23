"""Memory Systems Lab: virtual memory lab and local system monitor."""

import argparse
import csv
import io
import secrets
import threading
import time
import webbrowser
from collections import OrderedDict
from urllib.parse import urlsplit

from flask import Flask, Response, jsonify, render_template, request, session
from werkzeug.exceptions import HTTPException

from monitor import SystemMonitor
from simulator import Configuration, MemorySimulator


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=secrets.token_hex(32), MAX_CONTENT_LENGTH=16_384,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict")
    if test_config:
        app.config.update(test_config)
    simulations = OrderedDict()
    simulation_lock = threading.RLock()
    monitor = SystemMonitor()

    def current_simulation():
        now = time.monotonic()
        stale = [key for key, (_, timestamp) in simulations.items() if now - timestamp > 7200]
        for key in stale:
            simulations.pop(key, None)
        key = session.get("simulation_id")
        if key not in simulations:
            key = secrets.token_urlsafe(24)
            session["simulation_id"] = key
            simulations[key] = (MemorySimulator(), now)
        simulator, _ = simulations[key]
        simulations[key] = (simulator, now)
        simulations.move_to_end(key)
        while len(simulations) > 128:
            simulations.popitem(last=False)
        return simulator

    def json_body():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ValueError("Send a JSON object.")
        return body

    @app.before_request
    def protect_local_api():
        if urlsplit(f"http://{request.host}").hostname not in ("127.0.0.1", "localhost", "::1"):
            return jsonify(error="This app is available only on localhost."), 403
        origin = request.headers.get("Origin")
        if origin and urlsplit(origin).netloc != request.host:
            return jsonify(error="Cross-origin requests are not allowed."), 403

    @app.after_request
    def response_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/simulator")
    def get_simulator():
        with simulation_lock:
            return jsonify(current_simulation().snapshot())

    @app.post("/api/simulator/translate")
    def translate():
        body = json_body()
        with simulation_lock:
            simulator = current_simulation()
            simulator.translate(body.get("address"))
            return jsonify(simulator.snapshot())

    @app.post("/api/simulator/config")
    def configure():
        configuration = Configuration.from_dict(json_body())
        with simulation_lock:
            current_simulation()
            simulator = MemorySimulator(configuration)
            simulations[session["simulation_id"]] = (simulator, time.monotonic())
            return jsonify(simulator.snapshot())

    @app.post("/api/simulator/reset")
    def reset():
        with simulation_lock:
            config = current_simulation().config
            simulator = MemorySimulator(config)
            simulations[session["simulation_id"]] = (simulator, time.monotonic())
            return jsonify(simulator.snapshot())

    @app.get("/api/simulator/export")
    def export():
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        columns = ["index", "address", "page", "offset", "frame", "physical_address", "tlb_hit", "page_fault", "evicted_page", "cost_ns"]
        writer.writerow(columns)
        with simulation_lock:
            for event in current_simulation().history:
                writer.writerow([event[key] for key in columns])
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=memory-systems-lab-trace.csv"})

    @app.get("/api/system")
    def system():
        try:
            return jsonify(monitor.snapshot())
        except (OSError, RuntimeError):
            return jsonify(error="System statistics are temporarily unavailable. Retry shortly."), 503

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", app="Memory Systems Lab")

    @app.errorhandler(ValueError)
    def invalid_input(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(HTTPException)
    def http_error(error):
        if request.path.startswith("/api/"):
            return jsonify(error=error.description), error.code
        return error

    return app


app = create_app()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Memory Systems Lab memory lab locally.")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--open", action="store_true", help="Open the dashboard in your default browser")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")
    if args.open:
        timer = threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}"))
        timer.daemon = True
        timer.start()
    app.run(host="127.0.0.1", port=args.port, debug=False, threaded=True)
