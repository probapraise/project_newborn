from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .activity_watcher import process_snapshot
from .bridge_protocol import activity_snapshot_from_payload, decision_payload_from_json
from .db import connect, init_db
from .decision_logging import record_intervention_decision
from .event_dispatcher import _fetch_event_context
from .recovery import enter_recovery_mode

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
RECOVERY_DECISION_CATEGORIES = frozenset({"fatigue", "health", "sensory_overload", "schedule_change"})


def _json_bytes(payload: dict[str, Any] | list[Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def _pending_intervention_for_activity(activity_id: int | None) -> dict[str, Any] | None:
    if activity_id is None:
        return None
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id, timestamp, activity_event_id, schedule_block_id, risk_level, reason, status
            FROM intervention_events
            WHERE activity_event_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (activity_id,),
        ).fetchone()
    return _row_dict(row) if row is not None else None


def _pending_interventions(limit: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, timestamp, activity_event_id, schedule_block_id, risk_level, reason, status
            FROM intervention_events
            WHERE status = 'pending'
            ORDER BY timestamp, id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_row_dict(row) for row in rows]


def _safe_limit(value: str | None, default: int = 1) -> int:
    if value is None:
        return default
    limit = int(value)
    if limit <= 0 or limit > 20:
        raise ValueError("limit must be between 1 and 20.")
    return limit


def record_bridge_decision(event_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    decision = decision_payload_from_json(payload)
    recorded = record_intervention_decision(
        event_id,
        decision.choice,
        reason=decision.reason,
        duration_minutes=decision.duration_minutes,
        followup_action=decision.followup_action,
    )
    response: dict[str, Any] = {"decision": recorded}

    if decision.enter_recovery_mode:
        category = str(recorded.get("category") or "")
        if category not in RECOVERY_DECISION_CATEGORIES:
            raise ValueError("enter_recovery_mode is only allowed for fatigue, health, overload, or adjust_plan.")
        recovery = enter_recovery_mode(
            reason=f"intervention #{event_id}: {category} - {decision.reason or recorded.get('label', '')}",
            duration_hours=decision.recovery_duration_hours,
        )
        response["recovery"] = {
            "session_id": recovery.session_id,
            "prompt_path": str(recovery.prompt_path),
            "next_action": recovery.plan["next_action"],
        }

    return response


class LifeOpsRequestHandler(BaseHTTPRequestHandler):
    server_version = "LifeOpsCore/0.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any] | list[Any]) -> None:
        body = _json_bytes(payload)
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        body = self.rfile.read(length)
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object.")
        return payload

    def _send_error_json(self, status: HTTPStatus, message: str) -> None:
        self._send_json(status, {"error": message})

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                init_db()
                self._send_json(HTTPStatus.OK, {"status": "ok", "service": "lifeops-core"})
                return
            if parsed.path == "/interventions/pending":
                query = parse_qs(parsed.query)
                limit = _safe_limit(query.get("limit", [None])[0])
                self._send_json(HTTPStatus.OK, {"items": _pending_interventions(limit)})
                return
            self._send_error_json(HTTPStatus.NOT_FOUND, "not found")
        except ValueError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            payload = self._read_json()

            if parsed.path == "/events/activity":
                init_db()
                snapshot = activity_snapshot_from_payload(payload)
                activity_id, decision = process_snapshot(snapshot)
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "activity_id": activity_id,
                        "decision": {
                            "action": decision.action,
                            "reason": decision.reason,
                            "risk_level": decision.risk_level,
                        },
                        "intervention": _pending_intervention_for_activity(activity_id),
                    },
                )
                return

            if parsed.path.startswith("/interventions/") and parsed.path.endswith("/decision"):
                parts = parsed.path.strip("/").split("/")
                if len(parts) != 3:
                    raise ValueError("invalid intervention decision path.")
                event_id = int(parts[1])
                self._send_json(HTTPStatus.OK, record_bridge_decision(event_id, payload))
                return

            if parsed.path == "/recovery/enter":
                init_db()
                reason = str(payload.get("reason") or "").strip()
                if not reason:
                    raise ValueError("reason is required.")
                duration_hours = int(payload.get("duration_hours", 4))
                apply = bool(payload.get("apply", True))
                result = enter_recovery_mode(reason=reason, duration_hours=duration_hours, apply=apply)
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "session_id": result.session_id,
                        "applied": result.applied,
                        "prompt_path": str(result.prompt_path),
                        "next_action": result.plan["next_action"],
                    },
                )
                return

            self._send_error_json(HTTPStatus.NOT_FOUND, "not found")
        except (LookupError, ValueError, json.JSONDecodeError) as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))


def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, *, once: bool = False) -> None:
    init_db()
    server = ThreadingHTTPServer((host, port), LifeOpsRequestHandler)
    try:
        if once:
            server.handle_request()
        else:
            server.serve_forever()
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the LifeOps WSL localhost core API.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--once", action="store_true", help="Serve one request and exit.")
    args = parser.parse_args(argv)
    run_server(args.host, args.port, once=args.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
