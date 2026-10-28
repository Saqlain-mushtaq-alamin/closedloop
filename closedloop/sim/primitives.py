"""Robot primitives for T1 (plan Sec 9): the model writes logic, not IK.

Each primitive drives the T1Env given explicitly; policies compose them.
All motion is step-quantized so episodes stay deterministic (V1).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from closedloop.sim.env import T1Env


def move_to(env: T1Env, pos: tuple[float, float, float], steps: int = 60) -> None:
    """Move the hand toward pos over a fixed number of physics steps."""
    env.move_hand(pos, steps)


def open_gripper(env: T1Env) -> None:
    """Open the gripper (releases any grasped body)."""
    env.set_gripper(False)


def close_gripper(env: T1Env, force: float) -> None:
    """Close the gripper; grasps the cube if close, up to force newtons."""
    env.set_gripper(True, force)


def get_object_pose(env: T1Env, name: str) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Return (position, orientation) of a named body ('cube', 'pad')."""
    return env.object_pose(name)
