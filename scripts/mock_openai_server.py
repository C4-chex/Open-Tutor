#!/usr/bin/env python3
"""Tiny OpenAI-compatible mock server for CI smoke tests.

Endpoints:
- GET /v1/models
- POST /v1/chat/completions (stream + non-stream)
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


def _extract_user_text(messages: list[dict]) -> str:
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text.strip())
            if parts:
                return " ".join(part for part in parts if part)
    return ""


def _response_content(messages: list[dict]) -> str:
    """Return deterministic fixtures that satisfy the real response contracts."""
    system_text = " ".join(
        str(message.get("content", ""))
        for message in messages
        if isinstance(message, dict) and message.get("role") == "system"
    )
    if "creating practice questions" in system_text:
        questions = [
            {
                "question_type": "mc",
                "question": "What input does binary search require?",
                "options": {"A": "A sorted list", "B": "An unordered set", "C": "A graph", "D": "A stack"},
                "correct_answer": "A",
                "explanation": "Binary search relies on the ordering of elements to choose a half.",
            },
            {
                "question_type": "tf",
                "question": "Binary search discards half the remaining interval after each comparison.",
                "options": None,
                "correct_answer": "True",
                "explanation": "Comparing the midpoint lets the algorithm discard one half.",
            },
            {
                "question_type": "short_answer",
                "question": "Why is binary search unreliable on an unsorted list?",
                "options": None,
                "correct_answer": "Discarding a half may remove the target because the ordering invariant is absent.",
                "explanation": "The algorithm needs a sorted interval to preserve its search invariant.",
            },
        ]
        for question in questions:
            question["difficulty_layer"] = 1
            question["problem_metadata"] = {
                "core_concept": "binary search", "bloom_level": "understand",
                "potential_traps": [], "layer_justification": "Direct comprehension of the fixture",
                "skill_focus": "concept check", "source_section": "Binary Search Basics",
            }
        return json.dumps(questions)

    user_text = _extract_user_text(messages)
    return f"CI mock response: {user_text[:120]}" if user_text else "CI mock response."


class MockOpenAIHandler(BaseHTTPRequestHandler):
    server_version = "MockOpenAI/1.0"

    def _send_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_stream_event(self, payload: dict | str) -> None:
        if isinstance(payload, str):
            text = payload
        else:
            text = json.dumps(payload)
        self.wfile.write(f"data: {text}\n\n".encode("utf-8"))
        self.wfile.flush()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        model = self.server.model_name  # type: ignore[attr-defined]
        if path in ("/v1/models", "/models"):
            self._send_json(
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": model,
                            "object": "model",
                            "created": int(time.time()),
                            "owned_by": "mock",
                        }
                    ],
                },
            )
            return

        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != "/v1/chat/completions":
            self._send_json(404, {"error": "not_found"})
            return

        try:
            content_len = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_len = 0
        raw = self.rfile.read(content_len) if content_len > 0 else b"{}"

        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid_json"})
            return

        messages = payload.get("messages") if isinstance(payload, dict) else []
        if not isinstance(messages, list):
            messages = []
        stream = bool(payload.get("stream")) if isinstance(payload, dict) else False

        content = _response_content(messages)

        model = self.server.model_name  # type: ignore[attr-defined]
        created = int(time.time())

        if stream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            self._send_stream_event(
                {
                    "id": "chatcmpl-mock-stream",
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": content},
                            "finish_reason": None,
                        }
                    ],
                }
            )
            self._send_stream_event(
                {
                    "id": "chatcmpl-mock-stream",
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }
            )
            self._send_stream_event("[DONE]")
            return

        self._send_json(
            200,
            {
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "created": created,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 8,
                    "total_tokens": 20,
                },
            },
        )

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        # Keep CI logs clean unless explicitly tailed on failure.
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Start a tiny OpenAI-compatible mock server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--model", default="mock-smoke-model")
    args = parser.parse_args()

    httpd = ThreadingHTTPServer((args.host, args.port), MockOpenAIHandler)
    httpd.model_name = args.model  # type: ignore[attr-defined]
    print(f"mock-openai listening on http://{args.host}:{args.port} model={args.model}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
