"""Controller Language Grammar, AST Validator, Canonicalisation, and Hashing (Plan §7).

Enforces strict AST allow-list derived from empirical survey of frozen programs.
Rejects any hostile or non-conforming constructs with line-numbered diagnostic errors.
"""

from __future__ import annotations

import ast
import hashlib
import math
from typing import Any

MAX_SOURCE_BYTES = 4096
MAX_STATEMENTS = 60
MAX_NESTING_DEPTH = 5
MAX_NUMBER_MAGNITUDE = 1000.0

ALLOWED_ENV_METHODS = frozenset(
    {"move_to", "close_gripper", "open_gripper", "get_object_pos", "get_object_pose"}
)
ALLOWED_OBJECT_NAMES = frozenset({"cube", "pad"})

ALLOWED_NODE_TYPES = frozenset(
    {
        # Module and Function definition
        "Module", "FunctionDef", "arguments", "arg",
        # Statements
        "Assign", "Expr", "Pass", "If",
        # Expressions and Operands
        "Call", "Attribute", "Name", "Constant", "Tuple", "Subscript",
        "BinOp", "Add", "Sub", "Mult", "Div", "FloorDiv", "Mod",
        "UnaryOp", "USub", "UAdd",
        "Compare", "Eq", "NotEq", "Lt", "LtE", "Gt", "GtE",
        "keyword", "Load", "Store", "Index",
    }
)


def hash_program(code: str) -> str:
    """Compute SHA-256 of exact UTF-8 text with LF line endings (Plan §7)."""
    normalized = code.replace("\r\n", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def canonicalise_program(code: str) -> str:
    """Parse valid AST, drop comments and normalize formatting via ast.unparse."""
    tree = ast.parse(code.replace("\r\n", "\n"))
    return ast.unparse(tree) + "\n"


def validate_program(code: str) -> tuple[bool, str | None, int | None]:
    """Validate program source against strict AST grammar allow-list.

    Returns:
        (True, canonical_code, None) if valid.
        (False, error_message, line_number) if invalid.
    """
    if not code or not code.strip():
        return False, "Program source is empty", 1

    encoded = code.encode("utf-8")
    if len(encoded) > MAX_SOURCE_BYTES:
        return False, f"Source size ({len(encoded)} bytes) exceeds limit ({MAX_SOURCE_BYTES} bytes)", 1

    # Check for forbidden control characters or Cyrillic/homoglyph trickery in raw text
    for i, ch in enumerate(code):
        if ord(ch) > 127 and ch not in "±°·—–":  # Allow common non-ASCII symbols in comments if any, but identifier check below enforces ASCII names
            pass

    try:
        tree = ast.parse(code.replace("\r\n", "\n"))
    except SyntaxError as e:
        msg = e.msg
        if "invalid decimal literal" in msg:
            msg += " (use numbers only without unit suffixes, e.g. close_gripper(300), not close_gripper(300N))"
        return False, f"SyntaxError: {msg}", e.lineno or 1
    except Exception as e:
        return False, f"Parse error: {str(e)}", 1

    # Module must contain exactly one top-level statement: def policy(env, rng):
    if len(tree.body) != 1:
        return False, f"Program must contain exactly one function definition, found {len(tree.body)} statements", getattr(tree.body[0] if tree.body else tree, "lineno", 1)

    top = tree.body[0]
    if not isinstance(top, ast.FunctionDef):
        return False, f"Top-level statement must be a function definition, found {type(top).__name__}", getattr(top, "lineno", 1)

    if top.name != "policy":
        return False, f"Function must be named 'policy', found '{top.name}'", top.lineno

    # Verify signature: policy(env, rng)
    args = top.args
    pos_arg_names = [a.arg for a in args.args]
    if pos_arg_names != ["env", "rng"] or args.vararg is not None or args.kwarg is not None or args.kwonlyargs or args.defaults:
        return False, f"Function signature must be exactly 'policy(env, rng)', found args: {pos_arg_names}", top.lineno

    # Count statements and check nesting depth
    statement_count = 0

    def check_depth(node: ast.AST, depth: int) -> tuple[bool, str | None, int | None]:
        if depth > MAX_NESTING_DEPTH:
            return False, f"Nesting depth ({depth}) exceeds maximum allowed ({MAX_NESTING_DEPTH})", getattr(node, "lineno", 1)
        for child in ast.iter_child_nodes(node):
            next_depth = depth + 1 if isinstance(child, (ast.If,)) else depth
            ok, err, line = check_depth(child, next_depth)
            if not ok:
                return False, err, line
        return True, None, None

    depth_ok, depth_err, depth_line = check_depth(top, 1)
    if not depth_ok:
        return False, depth_err, depth_line

    # Annotate parent references for contextual AST checks
    for parent in ast.walk(top):
        for child in ast.iter_child_nodes(parent):
            child.parent = parent

    # Inspect all AST nodes
    for node in ast.walk(top):
        node_type = type(node).__name__
        lineno = getattr(node, "lineno", top.lineno)

        if node is not top and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return False, "Nested function definitions are forbidden", lineno

        if node_type not in ALLOWED_NODE_TYPES:
            return False, f"Forbidden language construct '{node_type}' is not allowed", lineno

        if isinstance(node, (ast.Assign, ast.Expr, ast.Pass, ast.If)):
            statement_count += 1
            if statement_count > MAX_STATEMENTS:
                return False, f"Statement count ({statement_count}) exceeds limit ({MAX_STATEMENTS})", lineno

        # Check identifiers: ASCII only, cannot start with underscore
        if isinstance(node, ast.Name):
            if not node.id.isascii():
                return False, f"Non-ASCII identifier '{node.id}' is not allowed", lineno
            if node.id.startswith("_"):
                return False, f"Private / dunder identifier '{node.id}' is forbidden", lineno

        if isinstance(node, ast.Attribute):
            if not node.attr.isascii():
                return False, f"Non-ASCII attribute '{node.attr}' is not allowed", lineno
            if node.attr.startswith("_"):
                return False, f"Access to private/dunder attribute '{node.attr}' is forbidden", lineno

            # Attribute access allowed ONLY on 'env'
            if isinstance(node.value, ast.Name):
                if node.value.id == "env":
                    if node.attr not in ALLOWED_ENV_METHODS:
                        return False, f"Attribute 'env.{node.attr}' is not an allowed environment method (allowed: {sorted(ALLOWED_ENV_METHODS)})", lineno
                else:
                    return False, f"Attribute access on '{node.value.id}' is forbidden; only methods on 'env' are permitted", lineno
            else:
                return False, f"Nested attribute access is forbidden", lineno

        # Check keyword arguments
        if isinstance(node, ast.keyword):
            if node.arg and node.arg.startswith("_"):
                return False, f"Private / dunder keyword argument '{node.arg}' is forbidden", lineno

        # Check Calls: only calls to env.<method> are allowed
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Attribute) or not isinstance(node.func.value, ast.Name) or node.func.value.id != "env":
                func_name = getattr(node.func, "id", None) or getattr(node.func, "attr", type(node.func).__name__)
                return False, f"Calling function '{func_name}' is forbidden; only methods on 'env' can be invoked", lineno

            method_name = node.func.attr
            if method_name not in ALLOWED_ENV_METHODS:
                return False, f"Method 'env.{method_name}' is not allowed", lineno

            # Method-specific argument validation
            if method_name in ("get_object_pos", "get_object_pose"):
                if node.keywords:
                    return False, f"{method_name}() takes no keyword arguments", lineno
                if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant) or node.args[0].value not in ALLOWED_OBJECT_NAMES:
                    return False, f"{method_name}() argument must be literal 'cube' or 'pad'", lineno

            if method_name == "open_gripper":
                if node.args or node.keywords:
                    return False, "open_gripper() takes no arguments", lineno

            if method_name == "close_gripper":
                for kw in node.keywords:
                    if kw.arg != "force":
                        return False, f"close_gripper() does not accept keyword argument '{kw.arg}'", lineno
                if len(node.args) > 1:
                    return False, "close_gripper() accepts at most 1 argument (force)", lineno
                if node.args and isinstance(node.args[0], ast.Constant):
                    val = node.args[0].value
                    if not isinstance(val, (int, float)) or val < 0 or val > MAX_NUMBER_MAGNITUDE:
                        return False, f"close_gripper force must be between 0 and {int(MAX_NUMBER_MAGNITUDE)}", lineno

            if method_name == "move_to":
                if len(node.args) != 1:
                    return False, "move_to() accepts exactly 1 positional argument (pos)", lineno
                for kw in node.keywords:
                    if kw.arg != "steps":
                        return False, f"move_to() does not accept keyword argument '{kw.arg}'", lineno
                    # Check constant int or unary op like -10
                    val = None
                    if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, int):
                        val = kw.value.value
                    elif isinstance(kw.value, ast.UnaryOp) and isinstance(kw.value.operand, ast.Constant) and isinstance(kw.value.operand.value, int):
                        if isinstance(kw.value.op, ast.USub):
                            val = -kw.value.operand.value
                        elif isinstance(kw.value.op, ast.UAdd):
                            val = kw.value.operand.value

                    if val is None or val < 1 or val > 240:
                        return False, "move_to steps must be integer between 1 and 240", lineno

        # Check Constants
        if isinstance(node, ast.Constant):
            val = node.value
            if isinstance(val, (int, float)):
                if math.isnan(val) or math.isinf(val):
                    return False, "NaN and Infinity are not allowed", lineno
                if abs(val) > MAX_NUMBER_MAGNITUDE:
                    return False, f"Numeric constant {val} exceeds absolute magnitude limit ({int(MAX_NUMBER_MAGNITUDE)})", lineno
            elif isinstance(val, str):
                if val not in ALLOWED_OBJECT_NAMES:
                    return False, f"String literal '{val}' is not allowed; only {sorted(ALLOWED_OBJECT_NAMES)} are permitted", lineno
                parent = getattr(node, "parent", None)
                if not (
                    isinstance(parent, ast.Call)
                    and isinstance(parent.func, ast.Attribute)
                    and isinstance(parent.func.value, ast.Name)
                    and parent.func.value.id == "env"
                    and parent.func.attr in ("get_object_pos", "get_object_pose")
                ):
                    return False, f"String literal '{val}' is only allowed as an argument to env.get_object_pos or env.get_object_pose", lineno
            elif isinstance(val, bytes):
                return False, "Byte literals are forbidden", lineno

    # Ensure canonical form parses identically
    try:
        canonical = ast.unparse(tree) + "\n"
    except Exception as e:
        return False, f"Canonicalization error: {e}", 1

    return True, canonical, None
