"""Rendered-footage Vision Judge for robot task execution (Plan §8, Phase 07).

Combines:
1. SAM 3.1 object segmentation (red cube, green pad).
2. Strict geometric check (cube centroid strictly inside pad boundary).
3. Multimodal Muse Spark 1.3 reasoning call with camera frame.
4. Frozen combination rule: geometric AND spark (Plan §8, DECISIONS.md).
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pybullet as p
from PIL import Image, ImageDraw, ImageFont

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
    "width": 256,
    "height": 256,
}


@dataclass
class JudgeVerdict:
    """Structured verdict from the vision judge."""

    pass_verdict: bool
    confidence: float
    reason: str
    geometric_pass: bool
    spark_pass: bool
    cube_box: tuple[int, int, int, int] | None = None
    pad_box: tuple[int, int, int, int] | None = None
    cube_centroid: tuple[float, float] | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


def check_centroid_in_pad(
    cube_box: tuple[int, int, int, int] | None,
    pad_box: tuple[int, int, int, int] | None,
    pad_margin_px: float = 2.0,
) -> bool:
    """Assert whether 2D centroid of detected cube lies strictly inside pad boundary.

    Enforces strict inequalities and a safety margin (pad_margin_px) away from pad boundary.
    """
    if cube_box is None or pad_box is None:
        return False

    cx1, cy1, cx2, cy2 = cube_box
    px1, py1, px2, py2 = pad_box

    if cx2 <= cx1 or cy2 <= cy1 or px2 <= px1 or py2 <= py1:
        return False

    c_x = (cx1 + cx2) / 2.0
    c_y = (cy1 + cy2) / 2.0

    # Strict inequality with inner margin
    in_x = (px1 + pad_margin_px) < c_x < (px2 - pad_margin_px)
    in_y = (py1 + pad_margin_px) < c_y < (py2 - pad_margin_px)
    return bool(in_x and in_y)


def combine_verdict(geometric_pass: bool, spark_pass: bool) -> bool:
    """Decision rule combining geometric mask test and Spark reasoning (Plan §8).

    Decided and frozen in DECISIONS.md: geometric AND spark.
    Provides high specificity: both physical SAM grounding and model reasoning must pass.
    """
    return bool(geometric_pass and spark_pass)


def render_judge_frame(
    env: T1Env,
    camera_cfg: dict[str, Any] | None = None,
) -> tuple[np.ndarray, str]:
    """Capture camera frame from the environment with visually grounded colors."""
    cfg = dict(DEFAULT_CAMERA_CFG)
    if camera_cfg:
        cfg.update(camera_cfg)

    width = int(cfg["width"])
    height = int(cfg["height"])

    # Ensure objects have visual colors: red cube, green pad
    p.changeVisualShape(env.cube, -1, rgbaColor=[0.85, 0.15, 0.15, 1.0], physicsClientId=env.cid)
    p.changeVisualShape(env.pad, -1, rgbaColor=[0.15, 0.80, 0.15, 1.0], physicsClientId=env.cid)

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

    return rgba, b64


def draw_overlay_image(
    rgba: np.ndarray,
    cube_box: tuple[int, int, int, int] | None,
    pad_box: tuple[int, int, int, int] | None,
    cube_centroid: tuple[float, float] | None,
    pass_verdict: bool,
    annotation: str = "",
) -> Image.Image:
    """Render bounding boxes, centroid crosshair, and status overlay onto image."""
    img = Image.fromarray(rgba).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Pad box in green
    if pad_box:
        px1, py1, px2, py2 = pad_box
        draw.rectangle([px1, py1, px2, py2], outline=(0, 230, 0), width=2)
        draw.text((px1 + 2, py1 + 2), "PAD", fill=(0, 230, 0))

    # Cube box in red
    if cube_box:
        cx1, cy1, cx2, cy2 = cube_box
        draw.rectangle([cx1, cy1, cx2, cy2], outline=(255, 30, 30), width=2)
        draw.text((cx1 + 2, cy1 + 2), "CUBE", fill=(255, 30, 30))

    # Centroid crosshair in yellow
    if cube_centroid:
        cx, cy = cube_centroid
        r = 4
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 0), outline=(0, 0, 0))

    # Status banner
    color = (0, 200, 0) if pass_verdict else (220, 20, 20)
    label = f"VERDICT: {'PASS' if pass_verdict else 'FAIL'} {annotation}".strip()
    draw.rectangle([0, 0, img.width, 18], fill=(30, 30, 30))
    draw.text((6, 2), label, fill=color)

    return img


class VisionJudge:
    """Evaluates robot task rollouts using camera footage, SAM 3.1, and Muse Spark."""

    def __init__(
        self,
        client: LLMClient | None = None,
        model: str = "muse-spark-1.3",
        segmentation_model: str = "sam-3.1",
        combination_rule: str = "geometric_and_spark",
        confidence_threshold: float = 0.70,
        prompt: str | None = None,
        camera_cfg: dict[str, Any] | None = None,
        cache: dict[str, Any] | None = None,
    ) -> None:
        self.client = client
        self.model = model
        self.segmentation_model = segmentation_model
        self.combination_rule = combination_rule
        self.confidence_threshold = confidence_threshold
        self.prompt = prompt or (
            "You are a vision judge for robot pick-and-place task T1 in simulation.\n"
            "Task Goal: The robot must pick up the cube and place it stably on top of the pad.\n"
            "Visual Grounding: The pad is the flat green rectangle on the table. The cube is the small red block.\n"
            "Examine the final camera image:\n"
            "1. Is the cube resting stably on top of the pad surface?\n"
            "2. Is the cube off the pad, tipped over on the table, or still held in air?\n\n"
            'Reply strictly with a single JSON object: {"pass": <bool>, "confidence": <float between 0 and 1>, "reason": "<short description>"}'
        )
        self.camera_cfg = camera_cfg or DEFAULT_CAMERA_CFG
        self.cache = cache if cache is not None else {}

    def judge_episode(
        self,
        env: T1Env,
        client_override: LLMClient | None = None,
    ) -> JudgeVerdict:
        """Evaluate an episode rollout at completion. Client is strictly required (no silent fake)."""
        client = client_override or self.client
        if client is None:
            raise ValueError(
                "VisionJudge requires an active LLMClient for evaluation; client cannot be None "
                "(Rule H4/H8: no silent mocks or fake fallbacks in evaluation paths)"
            )

        rgba, b64 = render_judge_frame(env, self.camera_cfg)
        img_sha = hashlib.sha256(b64.encode()).hexdigest()

        # Check Cache
        cache_key = hashlib.sha256(
            f"{self.model}:{self.segmentation_model}:{img_sha}:{self.prompt}".encode()
        ).hexdigest()[:24]

        if cache_key in self.cache:
            c = self.cache[cache_key]
            return JudgeVerdict(
                pass_verdict=bool(c["pass_verdict"]),
                confidence=float(c.get("confidence", 0.9)),
                reason=str(c.get("reason", "cached")),
                geometric_pass=bool(c.get("geometric_pass", False)),
                spark_pass=bool(c.get("spark_pass", False)),
                cube_box=tuple(c["cube_box"]) if c.get("cube_box") else None,
                pad_box=tuple(c["pad_box"]) if c.get("pad_box") else None,
                cube_centroid=tuple(c["cube_centroid"]) if c.get("cube_centroid") else None,
                tokens_in=int(c.get("tokens_in", 0)),
                tokens_out=int(c.get("tokens_out", 0)),
                cost_usd=float(c.get("cost_usd", 0.0)),
            )

        # 1. SAM 3.1 Segmentation (Plan §8, Task 1)
        res_cube = client.segment(b64, "red cube")
        res_pad = client.segment(b64, "green pad")

        cube_box = res_cube.get("box")
        pad_box = res_pad.get("box")

        cube_centroid = None
        if cube_box:
            cx1, cy1, cx2, cy2 = cube_box
            cube_centroid = ((cx1 + cx2) / 2.0, (cy1 + cy2) / 2.0)

        # 2. Geometric Check on SAM 3.1 Boxes
        geo_pass = check_centroid_in_pad(cube_box, pad_box)

        # 3. Muse Spark 1.3 Vision Reasoning
        resp_spark = client.complete(
            self.model,
            self.prompt,
            max_output_tokens=1024,
            images_b64=[b64],
            reasoning_effort="low",
            temperature=0.0,
            seed=42,
        )
        text = str(resp_spark.get("text", "")).strip()

        # Parse Spark JSON
        try:
            clean = text
            if clean.startswith("```"):
                lines = clean.splitlines()
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                clean = "\n".join(lines).strip()
            start = clean.find("{")
            end = clean.rfind("}")
            if start != -1 and end != -1:
                parsed = json.loads(clean[start : end + 1])
            else:
                parsed = json.loads(clean)

            s_pass = bool(parsed.get("pass", False))
            s_conf = float(parsed.get("confidence", 0.5))
            s_reason = str(parsed.get("reason", ""))

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

        # 4. Combine Verdicts (Plan §8, DECISIONS.md)
        if self.combination_rule == "geometric_and_spark":
            final_pass = combine_verdict(geo_pass, spark_pass)
        elif self.combination_rule == "spark_only":
            final_pass = spark_pass
        elif self.combination_rule == "geometric_only":
            final_pass = geo_pass
        else:
            raise ValueError(f"Unknown combination rule: {self.combination_rule}")

        total_tin = int(res_cube.get("tokens_in", 0)) + int(res_pad.get("tokens_in", 0)) + int(resp_spark.get("tokens_in", 0))
        total_tout = int(res_cube.get("tokens_out", 0)) + int(res_pad.get("tokens_out", 0)) + int(resp_spark.get("tokens_out", 0))
        total_cost = float(res_cube.get("cost_usd", 0.0)) + float(res_pad.get("cost_usd", 0.0)) + float(resp_spark.get("cost_usd", 0.0))

        verdict = JudgeVerdict(
            pass_verdict=final_pass,
            confidence=confidence,
            reason=reason,
            geometric_pass=geo_pass,
            spark_pass=spark_pass,
            cube_box=cube_box,
            pad_box=pad_box,
            cube_centroid=cube_centroid,
            tokens_in=total_tin,
            tokens_out=total_tout,
            cost_usd=round(total_cost, 6),
        )

        self.cache[cache_key] = {
            "pass_verdict": verdict.pass_verdict,
            "confidence": verdict.confidence,
            "reason": verdict.reason,
            "geometric_pass": verdict.geometric_pass,
            "spark_pass": verdict.spark_pass,
            "cube_box": verdict.cube_box,
            "pad_box": verdict.pad_box,
            "cube_centroid": verdict.cube_centroid,
            "tokens_in": verdict.tokens_in,
            "tokens_out": verdict.tokens_out,
            "cost_usd": verdict.cost_usd,
        }

        return verdict
