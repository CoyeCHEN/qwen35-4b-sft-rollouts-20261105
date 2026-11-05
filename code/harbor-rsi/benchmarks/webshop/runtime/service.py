#!/usr/bin/env python3
"""HTTP wrapper around Princeton WebShop's official text environment."""

from __future__ import annotations

import os
import threading


class ActionSession:
    def __init__(
        self, environment, goal_index, max_steps, product_set="official-small-1000"
    ):
        if max_steps <= 0:
            raise ValueError("max_steps must be positive")
        self.environment = environment
        self.product_set = product_set
        self.goal_index, self.max_steps = goal_index, max_steps
        self.steps, self.reward, self.done = 0, 0.0, False
        self.reason, self.last_action = None, None
        self.actions = []
        self.lock = threading.Lock()
        environment.reset(goal_index)

    def snapshot(self, details=False):
        payload = dict(
            instruction=self.environment.instruction_text,
            observation=self.environment.observation,
            available_actions=self.environment.get_available_actions(),
            steps=self.steps,
            max_steps=self.max_steps,
            remaining_actions=max(0, self.max_steps - self.steps),
            last_action=self.last_action,
            reward=self.reward,
            done=self.done,
            termination_reason=self.reason,
            goal_index=self.goal_index,
            product_set=self.product_set,
            protocol_version=2,
        )
        if details:
            payload["action_history"] = self.actions
        if details and self.done:
            state = self.environment.server.user_sessions[self.environment.session]
            payload.update(
                reward_info=state.get("verbose_info", {}),
                purchased_asin=state.get("asin"),
                selected_options=state.get("options", {}),
            )
        return payload

    def act(self, action):
        with self.lock:
            if self.done:
                return self.snapshot(), 409
            if not isinstance(action, str) or not action.strip():
                return {"error": "action must be a non-empty string"}, 400
            # Count every submitted action, including invalid actions, before execution.
            self.last_action = action.strip()
            self.steps += 1
            error = None
            try:
                _, reward, official_done, _ = self.environment.step(self.last_action)
                self.reward = float(reward or 0.0)
                if official_done:
                    self.done, self.reason = True, "purchase"
            except (AssertionError, ValueError, KeyError) as exc:
                error = str(exc) or type(exc).__name__
            if not self.done and self.steps >= self.max_steps:
                self.done, self.reason = True, "action_limit"
            self.actions.append(
                dict(step=self.steps, action=self.last_action, error=error)
            )
            payload = self.snapshot()
            if error:
                payload["error"] = error
            return payload, 400 if error else 200


def create_app(session):
    from flask import Flask, jsonify, request

    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify(ok=True, protocol_version=2, max_steps=session.max_steps)

    @app.get("/state")
    def state():
        with session.lock:
            return jsonify(session.snapshot())

    @app.post("/act")
    def act():
        body = request.get_json(silent=True)
        payload, code = session.act(
            body.get("action") if isinstance(body, dict) else None
        )
        return jsonify(payload), code

    @app.get("/result")
    def result():
        with session.lock:
            return jsonify(session.snapshot(details=True))

    return app


if __name__ == "__main__":
    from web_agent_site.envs.web_agent_text_env import WebAgentTextEnv
    from pathlib import Path

    product_set = os.environ.get("WEBSHOP_PRODUCT_SET", "official-small-1000")
    if product_set == "official-full-1.18m":
        from full_environment import create_full_environment

        environment = create_full_environment(Path(os.environ["WEBSHOP_FULL_ROOT"]))
    elif product_set == "official-small-1000":
        environment = WebAgentTextEnv(
            observation_mode="text", num_products=1000, human_goals=True
        )
    else:
        raise ValueError(f"Unsupported WEBSHOP_PRODUCT_SET: {product_set}")
    session = ActionSession(
        environment,
        int(os.environ.get("WEBSHOP_GOAL_INDEX", "0")),
        int(os.environ.get("WEBSHOP_MAX_STEPS", "100")),
        product_set,
    )
    create_app(session).run(host="0.0.0.0", port=3000, threaded=False)
