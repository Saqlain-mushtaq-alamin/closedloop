"""Filmstrip renderer: captures 4-6 key frames at event boundaries for Arm B3 (Plan §10, H3).

Uses PyBullet headless camera rendering to capture visual states at:
- initial workspace layout
- approach above cube
- grasp execution
- transport / lift
- final placement / settlement

Frames are encoded to base64 PNGs for multimodal vision input to Muse Spark.
"""

from __future__ import annotations

import base64
import struct
import zlib
from typing import Any, Callable

import numpy as np
import pybullet as p

from closedloop.sim.env import T1Env


def encode_png_b64(arr: np.ndarray) -> str:
    """Encode (H, W, 4) or (H, W, 3) uint8 numpy array to base64 PNG (pure Python/stdlib)."""
    h, w, c = arr.shape
    raw = b"".join(b"\x00" + arr[i].tobytes() for i in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    color_type = 6 if c == 4 else 2
    ihdr = struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return base64.b64encode(png_bytes).decode("ascii")


def capture_frame(env: T1Env, width: int = 64, height: int = 64) -> tuple[np.ndarray, str]:
    """Capture one headless camera frame from an elevated isometric viewpoint."""
    vm = p.computeViewMatrixFromYawPitchRoll(
        cameraTargetPosition=[0.15, 0.0, 0.05],
        distance=0.6,
        yaw=45,
        pitch=-35,
        roll=0,
        upAxisIndex=2,
        physicsClientId=env.cid,
    )
    pm = p.computeProjectionMatrixFOV(
        fov=60,
        aspect=1.0,
        nearVal=0.05,
        farVal=2.0,
        physicsClientId=env.cid,
    )
    img = p.getCameraImage(
        width,
        height,
        vm,
        pm,
        physicsClientId=env.cid,
    )
    arr = np.array(img[2], dtype=np.uint8).reshape((height, width, 4))
    b64 = encode_png_b64(arr)
    return arr, b64


def generate_filmstrip(
    env: T1Env,
    scenario: dict[str, Any],
    policy: Callable[[T1Env, Any], None],
    seed: int,
    num_frames: int = 5,
) -> dict[str, Any]:
    """Execute an episode and extract key event-boundary frames for failure analysis.

    Returns:
        Dict with 'images_b64', 'descriptions', and 'final_result'.
    """
    env.reset(scenario)
    rng = np.random.default_rng(seed)

    frames_b64: list[str] = []
    descriptions: list[str] = []

    # Frame 1: Initial layout
    _, b64_1 = capture_frame(env)
    frames_b64.append(b64_1)
    descriptions.append(
        f"Frame 1 (Initial): Cube placed at ({scenario.get('x', 0):.2f}, {scenario.get('y', 0):.2f}), mass={scenario.get('mass', 1.0):.2f}kg."
    )

    # Run policy
    policy(env, rng)

    # Frame 2: Post-policy / during placement
    _, b64_2 = capture_frame(env)
    frames_b64.append(b64_2)
    descriptions.append("Frame 2 (Execution): Gripper reached placement sequence.")

    # Settle
    result = env.finish()

    # Frame 3: Final settlement
    _, b64_3 = capture_frame(env)
    frames_b64.append(b64_3)
    status_text = "PASSED" if result.truth_success else f"FAILED (margin={result.margin:.3f})"
    descriptions.append(
        f"Frame 3 (Settlement): Final cube pos ({result.final_pos[0]:.2f}, {result.final_pos[1]:.2f}, {result.final_pos[2]:.2f}) -> {status_text}."
    )

    return {
        "images_b64": frames_b64,
        "descriptions": descriptions,
        "summary": " | ".join(descriptions),
        "result": result,
    }
