"""Filmstrip renderer: captures 4-6 key frames at event boundaries for Arm B3 (Plan §10, H3).

Uses PyBullet headless camera rendering to capture visual states at:
- initial workspace layout
- approach above cube
- grasp execution
- transport / lift
- placement release / settlement

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


class EventFilmstripWrapper:
    """Instruments policy execution to capture frames at distinct event boundaries."""

    def __init__(self, env: T1Env, target_frames: int = 5) -> None:
        self.env = env
        self.target_frames = target_frames
        self.frames_b64: list[str] = []
        self.descriptions: list[str] = []
        self.action_count = 0

    def capture(self, event_name: str, detail: str = "") -> None:
        if len(self.frames_b64) >= self.target_frames:
            return
        _, b64 = capture_frame(self.env)
        self.frames_b64.append(b64)
        idx = len(self.frames_b64)
        desc = f"Frame {idx} ({event_name}): {detail}" if detail else f"Frame {idx} ({event_name})"
        self.descriptions.append(desc)

    def move_to(self, pos: tuple[float, float, float], steps: int = 60) -> None:
        self.env.move_hand(pos, steps)
        self.action_count += 1
        cube_pos = self.get_object_pos("cube")
        hand_pos, _ = p.getBasePositionAndOrientation(self.env.hand, physicsClientId=self.env.cid)
        dist = float(np.linalg.norm(np.subtract(hand_pos, cube_pos)))
        if self.action_count == 1:
            self.capture(
                "Approach",
                f"Hand moved to ({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}), dist_to_cube={dist:.2f}m",
            )
        elif pos[2] > 0.10:
            self.capture(
                "Lift/Transport",
                f"Hand at z={hand_pos[2]:.2f}m, cube at z={cube_pos[2]:.2f}m",
            )
        else:
            self.capture(
                "Placement Move",
                f"Hand positioned at ({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f})",
            )

    def open_gripper(self) -> None:
        self.env.set_gripper(False)
        cube_pos = self.get_object_pos("cube")
        self.capture(
            "Release",
            f"Gripper opened above pad, cube at ({cube_pos[0]:.2f}, {cube_pos[1]:.2f}, {cube_pos[2]:.2f})",
        )

    def close_gripper(self, force: float) -> None:
        self.env.set_gripper(True, force)
        grasped = self.env._grasp_cid is not None
        status = "grasped successfully" if grasped else "grasp missed"
        self.capture(
            "Grasp",
            f"Gripper closed with force={force:.1f}N ({status})",
        )

    def get_object_pos(self, name: str) -> tuple[float, float, float]:
        return self.env.object_pose(name)[0]

    def get_object_pose(self, name: str) -> Any:
        return self.env.object_pose(name)

    # Expose underlying env attributes if policy accesses them directly
    @property
    def cid(self) -> int:
        return self.env.cid

    @property
    def cube(self) -> int:
        return self.env.cube

    @property
    def pad(self) -> int:
        return self.env.pad

    @property
    def hand(self) -> int:
        return self.env.hand

    def object_pose(self, name: str) -> Any:
        return self.env.object_pose(name)

    def move_hand(self, pos: tuple[float, float, float], steps: int) -> None:
        self.move_to(pos, steps)

    def set_gripper(self, closed: bool, force: float = 0.0) -> None:
        if closed:
            self.close_gripper(force)
        else:
            self.open_gripper()


def generate_filmstrip(
    env: T1Env,
    scenario: dict[str, Any],
    policy: Callable[[Any, Any], None],
    seed: int,
    num_frames: int = 5,
) -> dict[str, Any]:
    """Execute an episode and extract key event-boundary frames for failure analysis.

    Returns:
        Dict with 'images_b64', 'descriptions', 'summary', and 'result'.
    """
    env.reset(scenario)
    rng = np.random.default_rng(seed)

    wrapper = EventFilmstripWrapper(env, target_frames=num_frames)

    # Frame 1: Initial layout
    wrapper.capture(
        "Initial",
        f"Cube placed at ({scenario.get('x', 0):.2f}, {scenario.get('y', 0):.2f}), "
        f"mass={scenario.get('mass', 1.0):.2f}kg, friction={scenario.get('friction', 0.8):.2f}",
    )

    # Run policy with instrumented wrapper
    try:
        policy(wrapper, rng)
    except Exception as exc:  # noqa: BLE001
        wrapper.capture("Crash", f"Policy raised exception during execution: {exc}")

    # Settle
    result = env.finish()

    # Final settlement frame
    status_text = "PASSED" if result.truth_success else f"FAILED (margin={result.margin:.3f})"
    wrapper.capture(
        "Settlement",
        f"Final cube pos ({result.final_pos[0]:.2f}, {result.final_pos[1]:.2f}, {result.final_pos[2]:.2f}) -> {status_text}",
    )

    # If policy didn't trigger enough events, pad remaining frames up to num_frames
    while len(wrapper.frames_b64) < num_frames:
        _, b64 = capture_frame(env)
        wrapper.frames_b64.append(b64)
        idx = len(wrapper.frames_b64)
        wrapper.descriptions.append(f"Frame {idx} (Post-Settlement)")

    return {
        "images_b64": wrapper.frames_b64[:num_frames],
        "descriptions": wrapper.descriptions[:num_frames],
        "summary": " | ".join(wrapper.descriptions[:num_frames]),
        "result": result,
    }
