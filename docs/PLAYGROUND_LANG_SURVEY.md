# Controller Language Survey (Phase PA1)

**Date**: 2026-11-01  
**Status**: COMPLETE  
**Survey Scope**: All frozen programs across `runs/` (`cert-mint-02`, `cert-mint-03`, `round2-mint-01`, `demo-sessions-01`).

---

## 1. Inventory of Frozen Robot Programs

| Program Path | Program ID / Role | Commanded Grip Force | Bytes | AST Statements | Allowed Calls Used |
|---|---|---|---|---|---|
| `runs/cert-mint-03/program_initial.py` | `bec73dec45a88431` (Initial flawed policy) | `10 N` | 646 B | 14 | `get_object_pos`, `open_gripper`, `move_to`, `close_gripper` |
| `runs/cert-mint-03/program_final.py` | Minted candidate (Grasp repair v1) | `100 N` | 725 B | 16 | `get_object_pos`, `open_gripper`, `move_to`, `close_gripper` |
| `runs/round2-mint-01/program_initial.py` | `bec73dec45a88431` | `10 N` | 646 B | 14 | `get_object_pos`, `open_gripper`, `move_to`, `close_gripper` |
| `runs/round2-mint-01/program_final.py` | `5f74f7762ee1f378` (Certified v2 across 16 cells) | `300 N` | 727 B | 16 | `get_object_pos`, `open_gripper`, `move_to`, `close_gripper` |
| `runs/demo-sessions-01/session_*/session.json` | Recorded Muse Spark patches | `100 N` – `300 N` | 725 B | 16 | `get_object_pos`, `open_gripper`, `move_to`, `close_gripper` |

---

## 2. AST Nodes in Evidence

All verified frozen programs use only a strict, tiny subset of Python:

- **Root & Structure**: `Module`, `FunctionDef` (exactly one function named `policy` with arguments `env`, `rng`), `arguments`, `arg`
- **Statements**: `Assign`, `Expr`
- **Expressions**: `Call`, `Attribute` (only methods on `env`), `Name`, `Constant` (numeric `int`, `float`, and string literals `'cube'`, `'pad'`), `Tuple`, `Subscript` (constant integer indices), `BinOp` (operators: `Add`, `Sub`, `Mult`, `Div`), `UnaryOp` (`USub`), `keyword` (for `steps=...`)
- **No Loops**: Zero frozen programs use `for` or `while`.
- **No Imports**: Zero imports.
- **No Builtins / Meta-programming**: Zero calls to `eval`, `exec`, `open`, `__import__`, or dunder methods.

---

## 3. Method Allow-List & Hardware Limits

The validated grammar permits only calls to `env.<method>` where method is one of:
1. `env.move_to(pos, steps=...)`
2. `env.close_gripper(force)`
3. `env.open_gripper()`
4. `env.get_object_pos(name)` (name $\in$ `{'cube', 'pad'}`)
5. `env.get_object_pose(name)` (name $\in$ `{'cube', 'pad'}`)

### Gripper Force Verification (Open Item 2)
- Minimum commanded force in frozen set: **10 N** (`program_initial.py`)
- Maximum commanded force in frozen set: **300 N** (`round2-mint-01/program_final.py`)
- Environment implementation in `closedloop/sim/env.py`: `T1Env.set_gripper` has **no internal force cap**. Force is clamped solely by the hardware preset facade.
- Slip threshold physics: $m_{\max} = \frac{F}{1.2 \times 9.81}$:
  - `gripper_100N`: Clamped to 100 N $\implies m_{\max} \approx 8.495 \text{ kg}$. (Lifting $11.5 \text{ kg}$ requires $\approx 135.4 \text{ N}$, lifting $14.0 \text{ kg}$ requires $\approx 164.8 \text{ N}$).
  - `gripper_200N`: Clamped to 200 N $\implies m_{\max} \approx 16.989 \text{ kg}$.
  - `certified_default`: Pass-through without hardware clamp. Only robot preset eligible for `CERTIFIED` badge.
