"""Rendered-footage Vision Judge for robot task execution (Plan §8, Phase 07).

Combines:
1. Object mask extraction and geometric check (cube centroid within pad boundary).
2. Multimodal Muse Spark reasoning call with camera frame.
3. Frozen combination rule: geometric AND spark (Plan §8, DECISIONS.md).
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np
import pybullet as p

from closedloop.llm.client import LLMClient
from closedloop.llm.cost import CostMeter
from closedloop.repair.filmstrip import encode_png_b64
from closedloop.sim.env import T1Env


DEFAULT_CAMERA_CFG = {
    "cameraTargetPosition": [0.15, 0.0, 0.05],
    "distance": 0.6,
    "yaw": 45,
    "pitch": -35,
    "roll": 0,
    "upAxisIndex": 2,
    "fov": 60,
    "nearVal": 0.05,
    "farVal": 2.0,
    "width": 128,
    "height": 128,
}


@dataclass
class JudgeVerdict:
    """Structured verdict from the vision judge."""

    pass_verdict: bool
    confidence: float
    reason: str
    geometric_pass: bool
    spark_pass: bool
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


def check_centroid_in_pad(cube_mask: np.ndarray, pad_mask: np.ndarray) -> bool:
    """Assert whether the 2D centroid of the detected cube lies within the pad boundary."""
    cube_pts = np.argwhere(cube_mask)
    if len(cube_pts) == 0:
        return False
    # centroid (row, col)
    c_y, c_x = np.mean(cube_pts, axis=0)

    pad_pts = np.argwhere(pad_mask)
    if len(pad_pts) == 0:
        return False
    y_min, x_min = np.min(pad_pts, axis=0)
    y_max, x_max = np.max(pad_pts, axis=0)

    # Cube centroid must fall inside the pad's pixel bounding region
    return bool(y_min <= c_y <= y_max and x_min <= c_x <= x_max)


def combine_verdict(geometric_pass: bool, spark_pass: bool) -> bool:
    """Decision rule combining geometric mask test and Spark reasoning (Plan §8).

    Decided and frozen in DECISIONS.md: geometric AND spark.
    Provides high specificity: both the physical mask grounding and model reasoning must pass.
    """
    return bool(geometric_pass and spark_pass)


def render_judge_frame(
    env: T1Env,
    camera_cfg: dict[str, Any] | None = None,
) -> tuple[np.ndarray, str, np.ndarray, np.ndarray]:
    """Capture camera frame and segmentation masks for cube and pad."""
    cfg = dict(DEFAULT_CAMERA_CFG)
    if camera_cfg:
        cfg.update(camera_cfg)

    width = int(cfg["width"])
    height = int(cfg["height"])

    vm = p.computeViewMatrixFromYawPitchRoll(
        cameraTargetPosition=cfg["cameraTargetPosition"],
        distance=cfg["distance"],
        yaw=cfg["yaw"],
        pitch=cfg["pitch"],
        roll=cfg["roll"],
        upAxisIndex=cfg["upAxisIndex"],
        physicsClientId=env.cid,
    )
    pm = p.computeProjectionMatrixFOV(
        fov=cfg["fov"],
        aspect=float(width) / float(height),
        nearVal=cfg["nearVal"],
        farVal=cfg["farVal"],
        physicsClientId=env.cid,
    )
    img = p.getCameraImage(
        width,
        height,
        vm,
        pm,
        physicsClientId=env.cid,
    )
    rgba = np.array(img[2], dtype=np.uint8).reshape((height, width, 4))
    b64 = encode_png_b64(rgba)

    # In PyBullet, img[4] contains body segmentation mask
    seg = np.array(img[4], dtype=np.int32).reshape((height, width))
    cube_mask = (seg == env.cube)
    pad_mask = (seg == env.pad)

    return rgba, b64, cube_mask, pad_mask


class VisionJudge:
    """Evaluates robot task rollouts using camera footage, masks, and Muse Spark."""

    def __init__(
        self,
        client: LLMClient | None = None,
        model: str = "muse-spark-1.3",
        combination_rule: str = "geometric_and_spark",
        confidence_threshold: float = 0.70,
        camera_cfg: dict[str, Any] | None = None,
        cache: dict[str, Any] | None = None,
    ) -> None:
        self.client = client
        self.model = model
        self.combination_rule = combination_rule
        self.confidence_threshold = confidence_threshold
        self.camera_cfg = camera_cfg or DEFAULT_CAMERA_CFG
        self.cache = cache if cache is not None else {}

    def judge_episode(
        self,
        env: T1Env,
        client_override: LLMClient | None = None,
    ) -> JudgeVerdict:
        """Evaluate an episode rollout at completion."""
        client = client_override or self.client
        rgba, b64, cube_mask, pad_mask = render_judge_frame(env, self.camera_cfg)

        # 1. Geometric Check
        geo_pass = check_centroid_in_pad(cube_mask, pad_mask)

        # 2. Spark Multimodal Reasoning
        prompt = (
            "You are a vision judge for robot pick-and-place task T1 in simulation.\n"
            "Task Goal: The robot must pick up the cube and place it stably on top of the pad.\n"
            "Visual Grounding: The pad is the flat green rectangle on the table. The cube is the small block.\n"
            "Examine the final camera image:\n"
            "1. Is the cube resting stably on top of the pad surface?\n"
            "2. Is the cube off the pad, tipped over on the table, or still held in air?\n\n"
            'Reply strictly with a single JSON object: {"pass": <bool>, "confidence": <float between 0 and 1>, "reason": "<short description>"}'
        )

        spark_pass = geo_pass
        confidence = 0.90
        reason = "geometric assessment"
        tin = 0
        tout = 0
        cost = 0.0

        if client is not None:
            # Check cache
            cache_meta = {
                "model": self.model,
                "prompt": prompt,
                "image_sha256": hashlib.sha256(b64.encode()).hexdigest(),
            }
            phash = CostMeter.prompt_hash(cache_meta)

            if phash in self.cache:
                cached = self.cache[phash]
                spark_pass = bool(cached["pass"])
                confidence = float(cached.get("confidence", 0.90))
                reason = str(cached.get("reason", "cached verdict"))
                tin = int(cached.get("tokens_in", 0))
                tout = int(cached.get("tokens_out", 0))
                cost = float(cached.get("cost_usd", 0.0))
            else:
                resp = client.complete(
                    self.model,
                    prompt,
                    max_output_tokens=1024,
                    images_b64=[b64],
                    reasoning_effort="low",
                )
                text = str(resp.get("text", "")).strip()
                # Parse JSON
                try:
                    if text.startswith("```"):
                        lines = text.splitlines()
                        if lines[0].startswith("```"):
                            lines = lines[1:]
                        if lines and lines[-1].startswith("```"):
                            lines = lines[:-1]
                        text = "\n".join(lines).strip()
                    start = text.find("{")
                    end = text.rfind("}")
                    if start != -1 and end != -1:
                        parsed = json.loads(text[start : end + 1])
                    else:
                        parsed = json.loads(text)

                    s_pass = bool(parsed.get("pass", False))
                    s_conf = float(parsed.get("confidence", 0.5))
                    s_reason = str(parsed.get("reason", ""))

                    # Filter by confidence
                    if s_conf >= self.confidence_threshold:
                        spark_pass = s_pass
                    else:
                        spark_pass = False
                        s_reason += " (low confidence, rejected)"

                    confidence = s_conf
                    reason = s_reason
                except Exception as exc:  # noqa: BLE001
                    spark_pass = False
                    confidence = 0.0
                    reason = f"Parsing error: {exc}"

                tin = int(resp.get("tokens_in", 0))
                tout = int(resp.get("tokens_out", 0))
                cost = float(resp.get("cost_usd", 0.0))

                self.cache[phash] = {
                    "pass": spark_pass,
                    "confidence": confidence,
                    "reason": reason,
                    "tokens_in": tin,
                    "tokens_out": tout,
                    "cost_usd": cost,
                }

        # 3. Combine Verdicts (Plan §8, DECISIONS.md)
        if self.combination_rule == "geometric_and_spark":
            final_pass = combine_verdict(geo_pass, spark_pass)
        elif self.combination_rule == "spark_only":
            final_pass = spark_pass
        elif self.combination_rule == "geometric_only":
            final_pass = geo_pass
        else:
            raise ValueError(f"Unknown combination rule: {self.combination_rule}")

        return JudgeVerdict(
            pass_verdict=final_pass,
            confidence=confidence,
            reason=f"geo={geo_pass}, spark={spark_pass} ({reason})",
            geometric_pass=geo_pass,
            spark_pass=spark_pass,
            tokens_in=tin,
            tokens_out=tout,
            cost_usd=cost,
        )
