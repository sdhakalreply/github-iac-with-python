import hashlib
import hmac
import logging
import threading
import time

from flask import Flask, jsonify, request

from src import github_http, reconcile
from src.config import load_config
from src.github_auth import make_token_provider
from src.validator import validate_file
from src.webhook_filters import is_self_triggered

logger = logging.getLogger(__name__)

PORT = 5003
TEMPLATE_PATH = "stress_template.yaml"
_lock = threading.Lock()


def verify_signature(secret: str, body: bytes, header) -> bool:
    if not header:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)


def create_app(config: dict, token_provider=None) -> Flask:
    app = Flask(__name__)
    provide_token = token_provider or make_token_provider(config)

    @app.post("/webhook")
    def webhook():
        body = request.get_data()
        if not verify_signature(config["webhook_secret"], body, request.headers.get("X-Hub-Signature-256")):
            return jsonify({"error": "invalid signature"}), 401

        event = request.headers.get("X-GitHub-Event", "")
        payload = request.get_json(silent=True) or {}
        if event == "ping":
            return jsonify({"ok": "pong"}), 200
        if is_self_triggered(payload):
            return jsonify({"skipped": "bot"}), 200

        resource = reconcile.describe(payload)
        started = time.monotonic()
        try:
            ctx = {
                "org": config["github_org"],
                "token": provide_token,
                "base": config["github_api_base_url"],
            }
            with _lock:
                calls_before = github_http.get_stats()["total"]
                template = reconcile.build_index(validate_file(TEMPLATE_PATH))
                result = reconcile.reconcile_event(event, payload, template, ctx)
                api_calls = github_http.get_stats()["total"] - calls_before
        except Exception as exc:
            logger.error("Webhook %s for '%s' failed: %s", event, resource, exc)
            return jsonify({"error": "template unavailable"}), 502
        logger.info(
            "Webhook %s/%s for '%s': %s in %.0f ms, api_calls=%d",
            event, payload.get("action"), resource, result, (time.monotonic() - started) * 1000, api_calls,
        )
        return jsonify({"result": result}), 200

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config("vars.env")
    create_app(cfg).run(host="0.0.0.0", port=PORT, threaded=True)
