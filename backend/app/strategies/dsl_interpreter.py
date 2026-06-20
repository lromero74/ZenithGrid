"""
DSL Interpreter for Custom Trading Scripts

Provides a small, SANDBOXED domain-specific language that lets advanced users
write custom trading logic executed as a bot strategy.

DSL examples::

    limit('buy', 'BTC-USD', 0.01, price='-1%')
    if rsi(14) < 30: limit('buy', 'ETH-USD', 0.05)
    if price('BTC-USD') > 100000: market('sell', 'BTC-USD', all)

Security model
--------------
The sandbox is enforced by walking the AST — user text is **never** passed to
``eval()``, ``exec()``, or ``compile()``.  ``ast.parse()`` is the only entry
point; every node in the resulting tree is validated against a strict whitelist
before any evaluation takes place.  Anything not on the whitelist raises
``DSLError`` with the offending line and column.

Whitelisted AST node types
~~~~~~~~~~~~~~~~~~~~~~~~~~~
- ``Module`` — the root container
- ``Expr`` — bare expression statement (the wrapping node for a Call at the
  top level or in the body of an ``If``)
- ``If`` — ``if <condition>: <single action call>``
- ``Call`` — must have ``func`` as a bare ``Name`` from the callable whitelist;
  methods (``Attribute`` nodes) and calls-of-calls are rejected
- ``Compare`` — ``a < b``, ``a > b``, ``a <= b``, ``a >= b``, ``a == b``,
  ``a != b``
- ``BoolOp`` — ``and`` / ``or`` in conditions
- ``UnaryOp`` — ``USub`` (unary minus on a numeric literal) and ``Not``
- ``Constant`` — numeric/string literals
- ``Name`` (load context only) — **only** whitelisted names (data functions,
  action functions, and the bare name ``all``)
- ``keyword`` — for the ``price=`` named argument on ``limit()``
- Comparison operators: ``Lt``, ``LtE``, ``Gt``, ``GtE``, ``Eq``, ``NotEq``
- Boolean operators: ``And``, ``Or``

Every other node type — including ``Attribute``, ``Subscript``,
``Import``/``ImportFrom``, ``Assign``/``AugAssign``, ``FunctionDef``,
``Lambda``, comprehensions, ``Dict``/``Set``, ``Starred``, ``JoinedStr``
(f-strings), ``While``/``For``, ``Try``, ``With``, and walrus (``NamedExpr``)
— is **rejected** with a ``DSLError``.

Whitelisted callable names
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Data functions (read-only): ``price``, ``rsi``, ``macd``, ``bb_pct``, ``bb``
Action functions (produce OrderIntents): ``limit``, ``market``
Bare name (not callable): ``all``
"""

import ast
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class DSLError(Exception):
    """Raised when the DSL script is invalid or violates the security sandbox.

    Attributes:
        message: Human-readable description of the problem.
        line: 1-based line number in the source script (may be None).
        col: 0-based column offset (may be None).
    """

    def __init__(self, message: str, line: Optional[int] = None, col: Optional[int] = None):
        location = ""
        if line is not None:
            location = f" (line {line}"
            if col is not None:
                location += f", col {col}"
            location += ")"
        super().__init__(f"{message}{location}")
        self.message = message
        self.line = line
        self.col = col


@dataclass
class OrderIntent:
    """A trading action produced by evaluating a DSL script.

    Attributes:
        side: ``'buy'`` or ``'sell'``.
        symbol: Market pair, e.g. ``'BTC-USD'``.
        order_type: ``'limit'`` or ``'market'``.
        size: Numeric quantity, or ``None`` when ``size_is_all=True``.
        price_offset: Raw price modifier string such as ``'-1%'``, a literal
            float, or ``None`` for market orders with no offset.
        size_is_all: ``True`` when the script used the bare ``all`` keyword
            (sell entire position).
    """
    side: str
    symbol: str
    order_type: str  # 'limit' or 'market'
    size: Optional[float]
    price_offset: Optional[str] = field(default=None)
    size_is_all: bool = field(default=False)


# ---------------------------------------------------------------------------
# Whitelists
# ---------------------------------------------------------------------------

# Data-function names — callable in conditions and in action arguments
_DATA_FUNCTIONS = frozenset({"price", "rsi", "macd", "bb_pct", "bb"})

# Action-function names — callable only as statement-level or if-body expressions
_ACTION_FUNCTIONS = frozenset({"limit", "market"})

# All callable names (data + action)
_CALLABLE_NAMES = _DATA_FUNCTIONS | _ACTION_FUNCTIONS

# ``all`` is a bare name (not called) used as a size argument
_BARE_NAMES = frozenset({"all"})

# All names allowed as ``Name`` nodes
_ALLOWED_NAMES = _CALLABLE_NAMES | _BARE_NAMES

# Allowed comparison operators
_ALLOWED_CMP_OPS = (ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq)

# Allowed boolean operators
_ALLOWED_BOOL_OPS = (ast.And, ast.Or)

# Allowed unary operators
_ALLOWED_UNARY_OPS = (ast.USub, ast.Not)

# Whitelist of all node types that may appear anywhere in the AST tree
_ALLOWED_NODE_TYPES = frozenset({
    ast.Module,
    ast.Expr,
    ast.If,
    ast.Call,
    ast.Compare,
    ast.BoolOp,
    ast.UnaryOp,
    ast.Constant,
    ast.Name,
    ast.keyword,
    # Operators (not visited as standalone nodes but checked by type)
    ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq,
    ast.And, ast.Or,
    ast.USub, ast.Not,
    # Load context (Name nodes always have a ctx child)
    ast.Load,
})


# ---------------------------------------------------------------------------
# AST validation helpers
# ---------------------------------------------------------------------------


def _node_loc(node: ast.AST):
    """Return (line, col) tuple for an AST node, or (None, None) if unavailable."""
    return getattr(node, "lineno", None), getattr(node, "col_offset", None)


def _reject(node: ast.AST, msg: str) -> None:
    """Raise DSLError with location from node."""
    line, col = _node_loc(node)
    raise DSLError(msg, line=line, col=col)


def _validate_node_whitelist(node: ast.AST) -> None:
    """Recursively assert every node in the subtree is on the whitelist.

    This is the core security gate.  It is called on every node BEFORE any
    interpretation so that no crafted AST fragment can sneak past the
    structural checks below.
    """
    if type(node) not in _ALLOWED_NODE_TYPES:
        _reject(node, f"Forbidden AST node '{type(node).__name__}'")

    # Validate Name nodes: only whitelisted names in Load context
    if isinstance(node, ast.Name):
        if not isinstance(node.ctx, ast.Load):
            _reject(node, f"Name '{node.id}' in non-load context is not allowed")
        if node.id not in _ALLOWED_NAMES:
            _reject(node, f"Unknown name '{node.id}'")

    # Validate comparison operators
    if isinstance(node, ast.Compare):
        for op in node.ops:
            if not isinstance(op, _ALLOWED_CMP_OPS):
                _reject(node, f"Forbidden comparison operator '{type(op).__name__}'")

    # Validate boolean operators
    if isinstance(node, ast.BoolOp):
        if not isinstance(node.op, _ALLOWED_BOOL_OPS):
            _reject(node, f"Forbidden boolean operator '{type(node.op).__name__}'")

    # Validate unary operators
    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, _ALLOWED_UNARY_OPS):
            _reject(node, f"Forbidden unary operator '{type(node.op).__name__}'")

    # Validate Call nodes: func must be a bare whitelisted Name
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            _reject(node, "Calls must use a bare function name (no attribute access, no call chains)")
        if node.func.id not in _CALLABLE_NAMES:
            _reject(node, f"Unknown function '{node.func.id}'")

    for child in ast.iter_child_nodes(node):
        _validate_node_whitelist(child)


def _validate_action_call(node: ast.Call) -> None:
    """Structural + arity validation for a call that must be an action function.

    Checks:
    - ``func`` is a bare ``Name`` in ``_ACTION_FUNCTIONS``
    - ``limit()`` requires exactly 3 positional args
    - ``market()`` requires exactly 3 positional args and no keywords
    """
    if not isinstance(node.func, ast.Name) or node.func.id not in _ACTION_FUNCTIONS:
        _reject(node, f"Expected an action call (limit/market), got '{ast.dump(node.func)}'")

    line, col = _node_loc(node)
    fname = node.func.id

    if fname == "limit":
        if len(node.args) != 3:
            raise DSLError(
                "limit() requires exactly 3 positional arguments: limit(side, symbol, size)",
                line, col,
            )
        for kw in node.keywords:
            if kw.arg != "price":
                raise DSLError(f"Unknown keyword argument '{kw.arg}' in limit()", line, col)

    elif fname == "market":
        if len(node.args) != 3:
            raise DSLError(
                "market() requires exactly 3 positional arguments: market(side, symbol, size_or_all)",
                line, col,
            )
        if node.keywords:
            raise DSLError("market() does not accept keyword arguments", line, col)


def _validate_top_level_stmt(stmt: ast.stmt) -> None:
    """Validate that a top-level statement is either an action call or an if-block."""
    line, col = _node_loc(stmt)
    if isinstance(stmt, ast.Expr):
        # Must be an action call (limit/market), not a data function call
        if not isinstance(stmt.value, ast.Call):
            raise DSLError("Top-level expression must be an action call (limit or market)", line, col)
        call = stmt.value
        if not isinstance(call.func, ast.Name) or call.func.id not in _ACTION_FUNCTIONS:
            fname_str = call.func.id if isinstance(call.func, ast.Name) else "?"
            raise DSLError(
                f"Top-level call must be 'limit' or 'market', not '{fname_str}'",
                line, col,
            )
        _validate_action_call(call)
        return

    if isinstance(stmt, ast.If):
        # Condition: any whitelisted expression (already validated by whitelist pass)
        # Body: exactly one action call; no elif/else
        if stmt.orelse:
            raise DSLError("'else'/'elif' branches are not allowed in DSL if-statements", line, col)
        if len(stmt.body) != 1:
            raise DSLError("The 'if' body must contain exactly one action call", line, col)
        body_stmt = stmt.body[0]
        if not isinstance(body_stmt, ast.Expr) or not isinstance(body_stmt.value, ast.Call):
            raise DSLError("The 'if' body must contain exactly one action call", line, col)
        _validate_action_call(body_stmt.value)
        return

    raise DSLError(
        f"Only action calls and 'if <cond>: <action>' statements are allowed; "
        f"got '{type(stmt).__name__}'",
        line, col,
    )


# ---------------------------------------------------------------------------
# Public parse entry point
# ---------------------------------------------------------------------------


def parse_script(text: str) -> List[ast.stmt]:
    """Parse and validate a DSL script.

    Performs a two-phase check:
    1. Full AST whitelist scan — every node type and name is validated.
    2. Structural scan — top-level statements must be action calls or
       ``if <cond>: <action>`` blocks.

    Args:
        text: The raw DSL script text supplied by the user.

    Returns:
        List of validated ``ast.stmt`` objects that ``evaluate()`` can
        interpret.

    Raises:
        DSLError: If any security or structural constraint is violated.
    """
    try:
        tree = ast.parse(text, mode="exec")
    except SyntaxError as exc:
        raise DSLError(f"Syntax error: {exc.msg}", line=exc.lineno, col=exc.offset) from exc

    # Phase 1 — whitelist every node before doing anything else
    _validate_node_whitelist(tree)

    # Phase 2 — structural validation
    for stmt in tree.body:
        _validate_top_level_stmt(stmt)

    return tree.body


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------


def _resolve_data_call(call: ast.Call, context: Dict[str, Any]) -> Any:
    """Evaluate a data-function call (price, rsi, etc.) against the context.

    Args:
        call: A ``Call`` node whose ``func.id`` is in ``_DATA_FUNCTIONS``.
        context: Mapping of data values.  Keys are function names; values are
            either callables or nested dicts keyed by their first argument.

    Returns:
        The resolved numeric value.

    Raises:
        DSLError: If the argument is missing/unsupported or the data is absent.
    """
    fname = call.func.id
    line, col = _node_loc(call)

    if fname == "price":
        if len(call.args) != 1 or not isinstance(call.args[0], ast.Constant):
            raise DSLError("price() requires exactly one string argument: price('SYMBOL')", line, col)
        symbol = call.args[0].value
        prices = context.get("price", {})
        if callable(prices):
            return prices(symbol)
        if symbol not in prices:
            raise DSLError(f"price('{symbol}') not available in context", line, col)
        return float(prices[symbol])

    if fname == "rsi":
        if len(call.args) != 1 or not isinstance(call.args[0], ast.Constant):
            raise DSLError("rsi() requires exactly one integer period argument: rsi(14)", line, col)
        period = call.args[0].value
        rsi_data = context.get("rsi", {})
        if callable(rsi_data):
            return rsi_data(period)
        if period not in rsi_data:
            raise DSLError(f"rsi({period}) not available in context", line, col)
        return float(rsi_data[period])

    if fname == "macd":
        # macd() with no args → default 12/26/9 line value
        macd_data = context.get("macd", {})
        if callable(macd_data):
            return macd_data()
        if "line" not in macd_data:
            raise DSLError("macd() not available in context", line, col)
        return float(macd_data["line"])

    if fname in ("bb_pct", "bb"):
        # bb_pct() or bb(period) → Bollinger Band %B value
        bb_data = context.get("bb_pct", context.get("bb", {}))
        if callable(bb_data):
            if call.args and isinstance(call.args[0], ast.Constant):
                return bb_data(call.args[0].value)
            return bb_data()
        if isinstance(bb_data, (int, float)):
            return float(bb_data)
        raise DSLError(f"{fname}() not available in context", line, col)

    raise DSLError(f"Unknown data function '{fname}'", line, col)


def _eval_expr(node: ast.expr, context: Dict[str, Any]) -> Any:
    """Recursively evaluate a whitelisted expression node.

    Args:
        node: An AST expression node (already validated by ``parse_script``).
        context: Data context (see ``evaluate`` docstring).

    Returns:
        The Python value of the expression.
    """
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        # Only ``all`` reaches here (data/action function Names are never
        # standalone values in a condition)
        if node.id == "all":
            return "all"
        # Other names were validated; this branch should not be hit in practice
        raise DSLError(f"Unexpected bare name '{node.id}'", *_node_loc(node))

    if isinstance(node, ast.UnaryOp):
        operand = _eval_expr(node.operand, context)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.Not):
            return not operand

    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            result = True
            for value_node in node.values:
                result = result and _eval_expr(value_node, context)
            return result
        if isinstance(node.op, ast.Or):
            result = False
            for value_node in node.values:
                result = result or _eval_expr(value_node, context)
            return result

    if isinstance(node, ast.Compare):
        left = _eval_expr(node.left, context)
        result = True
        current = left
        for op, comparator_node in zip(node.ops, node.comparators):
            right = _eval_expr(comparator_node, context)
            if isinstance(op, ast.Lt):
                result = result and (current < right)
            elif isinstance(op, ast.LtE):
                result = result and (current <= right)
            elif isinstance(op, ast.Gt):
                result = result and (current > right)
            elif isinstance(op, ast.GtE):
                result = result and (current >= right)
            elif isinstance(op, ast.Eq):
                result = result and (current == right)
            elif isinstance(op, ast.NotEq):
                result = result and (current != right)
            current = right
        return result

    if isinstance(node, ast.Call):
        fname = node.func.id
        if fname in _DATA_FUNCTIONS:
            return _resolve_data_call(node, context)
        # Action functions are not valid in expression position
        raise DSLError(
            f"Action function '{fname}' cannot be used as an expression value",
            *_node_loc(node),
        )

    raise DSLError(f"Cannot evaluate node '{type(node).__name__}'", *_node_loc(node))


def _build_order_intent(call: ast.Call, context: Dict[str, Any]) -> OrderIntent:
    """Convert a validated action-call AST node into an ``OrderIntent``.

    Args:
        call: A ``Call`` whose ``func.id`` is ``'limit'`` or ``'market'``.
        context: Data context for resolving symbol prices.

    Returns:
        The ``OrderIntent`` represented by this call.

    Raises:
        DSLError: On argument count/type errors.
    """
    fname = call.func.id
    line, col = _node_loc(call)

    # ---- limit('side', 'symbol', size, price=...) ----
    if fname == "limit":
        if len(call.args) != 3:
            raise DSLError(
                "limit() requires 3 positional args: limit(side, symbol, size)", line, col
            )
        side = _eval_expr(call.args[0], context)
        symbol = _eval_expr(call.args[1], context)
        raw_size = _eval_expr(call.args[2], context)

        # price= keyword (optional)
        price_offset: Optional[str] = None
        for kw in call.keywords:
            if kw.arg == "price":
                kw_val = _eval_expr(kw.value, context)
                price_offset = str(kw_val)
            else:
                raise DSLError(f"Unknown keyword argument '{kw.arg}' in limit()", line, col)

        if raw_size == "all":
            return OrderIntent(
                side=side, symbol=symbol, order_type="limit",
                size=None, price_offset=price_offset, size_is_all=True,
            )
        return OrderIntent(
            side=side, symbol=symbol, order_type="limit",
            size=float(raw_size), price_offset=price_offset,
        )

    # ---- market('side', 'symbol', size_or_all) ----
    if fname == "market":
        if len(call.args) != 3:
            raise DSLError(
                "market() requires 3 positional args: market(side, symbol, size_or_all)", line, col
            )
        if call.keywords:
            raise DSLError("market() does not accept keyword arguments", line, col)
        side = _eval_expr(call.args[0], context)
        symbol = _eval_expr(call.args[1], context)
        raw_size = _eval_expr(call.args[2], context)

        if raw_size == "all":
            return OrderIntent(
                side=side, symbol=symbol, order_type="market",
                size=None, size_is_all=True,
            )
        return OrderIntent(
            side=side, symbol=symbol, order_type="market",
            size=float(raw_size),
        )

    raise DSLError(f"Unknown action function '{fname}'", line, col)


# ---------------------------------------------------------------------------
# Public evaluate entry point
# ---------------------------------------------------------------------------


def evaluate(parsed: List[ast.stmt], context: Dict[str, Any]) -> List[OrderIntent]:
    """Evaluate a parsed DSL script against a market-data context.

    Args:
        parsed: The list of ``ast.stmt`` objects returned by ``parse_script``.
        context: A dict providing market data to the script.  Expected keys:

            ``"price"``
                Dict ``{symbol: float}`` **or** a callable ``(symbol) -> float``.

            ``"rsi"``
                Dict ``{period: float}`` **or** a callable ``(period) -> float``.

            ``"macd"``
                Dict ``{"line": float, ...}`` **or** a callable ``() -> float``.

            ``"bb_pct"`` / ``"bb"``
                A ``float`` **or** a callable ``(period=None) -> float``.

    Returns:
        List of ``OrderIntent`` objects for every action whose condition was
        satisfied (unconditional calls always produce one intent).

    Raises:
        DSLError: If evaluation fails due to missing data or invalid arguments.
    """
    intents: List[OrderIntent] = []

    for stmt in parsed:
        if isinstance(stmt, ast.Expr):
            # Unconditional action call
            intents.append(_build_order_intent(stmt.value, context))

        elif isinstance(stmt, ast.If):
            # Conditional action: evaluate condition; act if truthy
            condition_result = _eval_expr(stmt.test, context)
            if condition_result:
                body_call = stmt.body[0].value
                intents.append(_build_order_intent(body_call, context))

    return intents
