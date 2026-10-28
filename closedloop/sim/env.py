"""T1 pick-and-place environment: deterministic, headless (DIRECT) PyBullet.

Grasp model (explicit, documented): a collision-free kinematic hand;
closing within grasp radius attaches a fixed constraint; lifting with
force below mass*g*SLIP_FACTOR slips. No arm IK: policies command the hand.
SimResult maps into the plan's EpisodeResult in Phase 03.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np
import pybullet as p

from closedloop.sim import predicates
from closedloop.sim import primitives as prim

TIMESTEP = 1.0 / 240.0
STABLE_STEPS = 20
PAD_POS = (0.25, 0.0)
PAD_TOP_Z = 0.01
CUBE_HALF = 0.02
GRASP_RADIUS = 0.05
SLIP_FACTOR = 1.2
RADIUS = 0.03
STAB_TOL = 0.005
CONTACT_GAP = 0.005
SPEED_TOL = 0.05


@dataclass
class SimResult:
    """Outcome of one episode (V1 hash covers every field that matters)."""

    truth_success: bool
    truth_success_alt: bool
    margin: float
    final_pos: tuple[float, float, float]
    steps: int
    agreed: bool
    trace: list[tuple] = field(default_factory=list, compare=False)

    def result_hash(self) -> str:
        """Deterministic hash for V1 (margin/pose rounded, trace excluded)."""
        key = (
            self.truth_success,
            self.truth_success_alt,
            round(self.margin, 9),
            tuple(round(c, 9) for c in self.final_pos),
            self.steps,
        )
        return hashlib.sha256(repr(key).encode()).hexdigest()


class T1Env:
    """Floating-hand T1 world. One physics client per instance."""

    def __init__(self) -> None:
        self.cid = p.connect(p.DIRECT)
        p.setTimeStep(TIMESTEP)
        p.setGravity(0, 0, -9.81)
        self.steps = 0
        self._grasp_cid: int | None = None
        self._grasp_force = 0.0
        self._closed = False

    def close(self) -> None:
        """Disconnect the physics client (idempotent)."""
        if not self._closed:
            self._closed = True
            p.disconnect(self.cid)

    def reset(self, scenario: dict) -> None:
        """Rebuild the world from a scenario (deterministic layout)."""
        p.resetSimulation(physicsClientId=self.cid)
        p.setGravity(0, 0, -9.81, physicsClientId=self.cid)
        p.createMultiBody(
            baseMass=0,
            baseCollisionShapeIndex=p.createCollisionShape(
                p.GEOM_PLANE, physicsClientId=self.cid
            ),
            basePosition=[0, 0, 0],
            physicsClientId=self.cid,
        )
        self.pad = p.createMultiBody(
            baseMass=0,
            baseCollisionShapeIndex=p.createCollisionShape(
                p.GEOM_BOX, halfExtents=[0.06, 0.06, 0.005],
                physicsClientId=self.cid,
            ),
            basePosition=[PAD_POS[0], PAD_POS[1], 0.005],
            physicsClientId=self.cid,
        )
        yaw = p.getQuaternionFromEuler([0, 0, float(scenario["yaw"])])
        self.cube = p.createMultiBody(
            baseMass=float(scenario["mass"]),
            baseCollisionShapeIndex=p.createCollisionShape(
                p.GEOM_BOX, halfExtents=[CUBE_HALF] * 3,
                physicsClientId=self.cid,
            ),
            basePosition=[float(scenario["x"]), float(scenario["y"]), CUBE_HALF],
            baseOrientation=yaw,
            physicsClientId=self.cid,
        )
        p.changeDynamics(
            self.cube, -1, lateralFriction=float(scenario["friction"]),
            physicsClientId=self.cid,
        )
        self.mass = float(scenario["mass"])
        self.hand = p.createMultiBody(
            baseMass=0,
            baseCollisionShapeIndex=p.createCollisionShape(
                p.GEOM_SPHERE, radius=0.015, physicsClientId=self.cid
            ),
            basePosition=[0, 0, 0.15],
            physicsClientId=self.cid,
        )
        p.setCollisionFilterGroupMask(
            self.hand, -1, 0, 0, physicsClientId=self.cid
        )
        self.steps = 0
        self._grasp_cid = None
        self.trace: list[tuple] = []

    # -- primitives ------------------------------------------------------
    def object_pose(self, name: str):
        """Return (position, orientation) of the cube or the pad."""
        body = self.cube if name == "cube" else self.pad
        return p.getBasePositionAndOrientation(body, physicsClientId=self.cid)

    def move_hand(self, pos: tuple[float, float, float], steps: int) -> None:
        """Interpolate the hand to pos over a fixed number of steps."""
        start, _ = p.getBasePositionAndOrientation(
            self.hand, physicsClientId=self.cid
        )
        for i in range(1, steps + 1):
            alpha = i / steps
            nxt = tuple(s + (t - s) * alpha for s, t in zip(start, pos))
            p.resetBasePositionAndOrientation(
                self.hand, nxt, [0, 0, 0, 1], physicsClientId=self.cid
            )
            self._step()

    def set_gripper(self, closed: bool, force: float = 0.0) -> None:
        """Close (grasp if near) or open (release) the gripper."""
        if closed:
            hand_pos, _ = p.getBasePositionAndOrientation(
                self.hand, physicsClientId=self.cid
            )
            cube_pos, _ = p.getBasePositionAndOrientation(
                self.cube, physicsClientId=self.cid
            )
            dist = float(np.linalg.norm(np.subtract(hand_pos, cube_pos)))
            if dist <= GRASP_RADIUS and self._grasp_cid is None:
                offset = tuple(c - h for c, h in zip(cube_pos, hand_pos))
                self._grasp_cid = p.createConstraint(
                    self.hand, -1, self.cube, -1, p.JOINT_FIXED,
                    [0, 0, 0], [0, 0, 0], offset,
                    physicsClientId=self.cid,
                )
                self._grasp_force = force
        elif self._grasp_cid is not None:
            p.removeConstraint(self._grasp_cid, physicsClientId=self.cid)
            self._grasp_cid = None

    # -- episodes ---------------------------------------------------------
    def _step(self) -> None:
        p.stepSimulation(physicsClientId=self.cid)
        self.steps += 1
        if self._grasp_cid is not None:
            hand_pos, _ = p.getBasePositionAndOrientation(
                self.hand, physicsClientId=self.cid
            )
            if hand_pos[2] > 0.07 and self._grasp_force < self.mass * 9.81 * SLIP_FACTOR:
                p.removeConstraint(self._grasp_cid, physicsClientId=self.cid)
                self._grasp_cid = None
        cube_pos, _ = p.getBasePositionAndOrientation(
            self.cube, physicsClientId=self.cid
        )
        self.trace.append((self.steps, tuple(cube_pos)))

    def run_episode(self, policy, scenario: dict, seed: int) -> SimResult:
        """Reset, run a policy(api, rng) function, settle, and evaluate."""
        self.reset(scenario)
        rng = np.random.default_rng(seed)
        policy(self, rng)
        tail: list[tuple[float, float, float]] = []
        for _ in range(STABLE_STEPS):
            self._step()
            tail.append(self.trace[-1][1])
        final, _ = p.getBasePositionAndOrientation(
            self.cube, physicsClientId=self.cid
        )
        vel, _ = p.getBaseVelocity(self.cube, physicsClientId=self.cid)
        speed = float(np.linalg.norm(vel))
        contacts = p.getContactPoints(self.cube, self.pad, physicsClientId=self.cid)
        bottom_gap = final[2] - CUBE_HALF - PAD_TOP_Z if contacts else 9.0
        pred1, pred2, margin = predicates.evaluate(
            final, tail, (PAD_POS[0], PAD_POS[1], PAD_TOP_Z + CUBE_HALF),
            RADIUS, STAB_TOL, CONTACT_GAP, bottom_gap, speed, SPEED_TOL,
        )
        agreed = pred1 == pred2
        success = bool(pred1 and pred2)
        return SimResult(
            truth_success=success,
            truth_success_alt=bool(pred2),
            margin=float(margin),
            final_pos=tuple(round(c, 9) for c in final),
            steps=self.steps,
            agreed=agreed,
            trace=list(self.trace),
        )


# -- scripted policies ----------------------------------------------------
def noop_policy(env: T1Env, rng: np.random.Generator) -> None:
    """Do nothing (V2 negative control)."""


def random_policy(env: T1Env, rng: np.random.Generator) -> None:
    """Seeded random flailing (V2 negative control)."""
    for _ in range(8):
        choice = rng.integers(0, 3)
        if choice == 0:
            prim.move_to(
                env,
                (float(rng.uniform(-0.2, 0.3)), float(rng.uniform(-0.2, 0.2)),
                 float(rng.uniform(0.02, 0.25))),
                steps=30,
            )
        elif choice == 1:
            prim.close_gripper(env, float(rng.uniform(0, 30)))
        else:
            prim.open_gripper(env)


def good_policy(env: T1Env, rng: np.random.Generator) -> None:
    """Hand-written pick-and-place using object pose (positive reference)."""
    cube_pos, _ = prim.get_object_pose(env, "cube")
    above = (cube_pos[0], cube_pos[1], 0.15)
    prim.move_to(env, above, steps=40)
    prim.move_to(env, (cube_pos[0], cube_pos[1], cube_pos[2] + 0.03), steps=40)
    prim.close_gripper(env, 30.0)
    prim.move_to(env, above, steps=40)
    prim.move_to(env, (PAD_POS[0], PAD_POS[1], 0.15), steps=60)
    prim.move_to(env, (PAD_POS[0], PAD_POS[1], 0.06), steps=40)
    prim.open_gripper(env)
    prim.move_to(env, (PAD_POS[0], PAD_POS[1], 0.15), steps=40)
