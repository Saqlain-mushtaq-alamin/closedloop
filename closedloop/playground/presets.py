"""Robot and Task Presets and Sandboxed Policy Facade (Plan §6).

Defines:
- Robot presets: 'certified_default', 'gripper_100N', 'gripper_200N'.
- Task presets: 'light_parts', 'mixed_bin' (distribution D), 'heavy_parts'.
- PlaygroundPolicyFacade: Hardware clamping, coordinate protection, step budgeting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from closedloop.sim.env import T1Env

MAX_STEPS_PER_EPISODE = 3000

# Physical limits for coordinates (workspace safety bounds)
X_BOUNDS = (-0.5, 0.5)
Y_BOUNDS = (-0.5, 0.5)
Z_BOUNDS = (0.0, 0.5)

ROBOT_PRESETS: dict[str, dict[str, Any]] = {
    "certified_default": {
        "name": "Certified Default Gripper",
        "description": "Identity facade: forces pass through exactly as certified evidence runs.",
        "force_limit_n": None,
        "eligible_for_certified": True,
    },
    "gripper_100N": {
        "name": "Standard 100 N Gripper",
        "description": "Hardware limit clamps commanded grip force to 100 N (max liftable mass ~8.49 kg).",
        "force_limit_n": 100.0,
        "eligible_for_certified": False,
    },
    "gripper_200N": {
        "name": "Heavy-Duty 200 N Gripper",
        "description": "Hardware limit clamps commanded grip force to 200 N (max liftable mass ~16.99 kg).",
        "force_limit_n": 200.0,
        "eligible_for_certified": False,
    },
}

TASK_PRESETS: dict[str, dict[str, Any]] = {
    "light_parts": {
        "name": "Light Parts Bin (1 to 5 kg)",
        "bounds": {
            "mass": [1.0, 5.0],
            "friction": [0.1, 1.0],
            "x": [-0.15, 0.15],
            "y": [-0.15, 0.15],
            "yaw": [-0.5, 0.5],
        },
        "is_certified_distribution": False,
    },
    "mixed_bin": {
        "name": "Mixed Bin (Distribution D: 1 to 11.5 kg)",
        "bounds": {
            "mass": [1.0, 11.5],
            "friction": [0.1, 1.0],
            "x": [-0.15, 0.15],
            "y": [-0.15, 0.15],
            "yaw": [-0.5, 0.5],
        },
        "is_certified_distribution": True,
    },
    "heavy_parts": {
        "name": "Heavy Parts Bin (6 to 14 kg)",
        "bounds": {
            "mass": [6.0, 14.0],
            "friction": [0.1, 1.0],
            "x": [-0.15, 0.15],
            "y": [-0.15, 0.15],
            "yaw": [-0.5, 0.5],
        },
        "is_certified_distribution": False,
    },
}


class StepBudgetExceeded(RuntimeError):
    """Raised when an episode exceeds the 3000 step budget (Rule H13 failure)."""


@dataclass
class HardwareClampEvent:
    commanded_force: float
    applied_force: float
    reason: str


class PlaygroundPolicyFacade:
    """Restricted policy facade wrapping T1Env with preset hardware limits and safeguards."""

    def __init__(self, env: T1Env, robot_preset: str | dict[str, Any] = "certified_default") -> None:
        if isinstance(robot_preset, dict):
            found_key = None
            for k, cfg in ROBOT_PRESETS.items():
                if cfg == robot_preset or cfg.get("name") == robot_preset.get("name"):
                    found_key = k
                    break
            self._robot_preset = found_key or robot_preset.get("name", "custom")
            self._preset_cfg = robot_preset
        else:
            if robot_preset not in ROBOT_PRESETS:
                raise ValueError(f"Unknown robot preset: {robot_preset} (valid: {list(ROBOT_PRESETS.keys())})")
            self._robot_preset = robot_preset
            self._preset_cfg = ROBOT_PRESETS[robot_preset]
        self._env = env
        self._force_limit = self._preset_cfg.get("force_limit_n")
        self.clamp_events: list[HardwareClampEvent] = []

    def _check_step_budget(self, additional_steps: int) -> None:
        if self._env.steps + additional_steps > MAX_STEPS_PER_EPISODE:
            raise StepBudgetExceeded(
                f"Episode step budget ({MAX_STEPS_PER_EPISODE}) exceeded: "
                f"current {self._env.steps} + requested {additional_steps}"
            )

    def move_to(self, pos: tuple[float, float, float], steps: int = 60) -> None:
        """Clamp coordinates and steps within physical safety limits, then step."""
        # Clamp steps
        steps_clamped = max(1, min(240, int(steps)))
        self._check_step_budget(steps_clamped)

        # Clamp positions to workspace bounding box
        clamped_x = max(X_BOUNDS[0], min(X_BOUNDS[1], float(pos[0])))
        clamped_y = max(Y_BOUNDS[0], min(Y_BOUNDS[1], float(pos[1])))
        clamped_z = max(Z_BOUNDS[0], min(Z_BOUNDS[1], float(pos[2])))
        clamped_pos = (clamped_x, clamped_y, clamped_z)

        self._env.move_hand(clamped_pos, steps=steps_clamped)

    def open_gripper(self) -> None:
        """Open the gripper to release any grasped object."""
        self._env.set_gripper(False)

    def close_gripper(self, force: float = 100.0) -> None:
        """Close gripper, clamping force to robot preset hardware limits."""
        cmd_force = float(force)
        if self._force_limit is not None and cmd_force > self._force_limit:
            applied = self._force_limit
            self.clamp_events.append(
                HardwareClampEvent(
                    commanded_force=cmd_force,
                    applied_force=applied,
                    reason=f"commanded {cmd_force:.1f} N, applied {applied:.1f} N (hardware limit)",
                )
            )
        else:
            applied = cmd_force

        self._env.set_gripper(True, force=applied)

    def get_object_pos(self, name: str) -> tuple[float, float, float]:
        """Get (x, y, z) position of target object ('cube' or 'pad')."""
        if name not in ("cube", "pad"):
            raise ValueError(f"Unknown object: {name}")
        return self._env.object_pose(name)[0]

    def get_object_pose(self, name: str) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
        """Get (pos, quat) of target object ('cube' or 'pad')."""
        if name not in ("cube", "pad"):
            raise ValueError(f"Unknown object: {name}")
        return self._env.object_pose(name)
