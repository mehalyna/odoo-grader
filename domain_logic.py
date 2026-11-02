"""Logical equivalence check for Odoo domains, without eval.

The domain text is read with ast.literal_eval, which accepts Python literals
only and never executes code. The parsed domain is compared with the target
"active companies whose country code is UA" over every truth assignment of the
recognised conditions. Unrecognised conditions are treated as unknown variables,
so an unfamiliar field gives REVIEW, not FAIL.
"""

import ast
import itertools
from dataclasses import dataclass

MAX_UNKNOWN_CONDITIONS = 10


@dataclass(frozen=True)
class DomainVerdict:
    status: str  # "PASS", "FAIL" or "REVIEW"
    message: str


class UnsupportedDomain(Exception):
    """The domain text is not a plain Odoo domain literal."""


def analyze_company_domain(domain_text):
    """Compare a stored ir.filters domain with 'active companies in Ukraine'."""
    try:
        formula, unknown_count = parse_domain(domain_text)
    except UnsupportedDomain as error:
        return DomainVerdict("REVIEW", f"Unsupported domain expression: {error}.")
    if unknown_count > MAX_UNKNOWN_CONDITIONS:
        return DomainVerdict("REVIEW", f"Too many unrecognised conditions ({unknown_count}) to check equivalence.")

    unresolved = None
    for company, ukraine in itertools.product((True, False), repeat=2):
        target = company and ukraine
        env = {"company": company, "ukraine": ukraine}
        outcomes = {
            evaluate(formula, env, unknown)
            for unknown in itertools.product((True, False), repeat=unknown_count)
        }
        if outcomes == {target}:
            continue
        if len(outcomes) == 1:
            outcome = outcomes.pop()
            return DomainVerdict(
                "FAIL",
                f"Domain does not select exactly active Ukrainian companies: for a record with "
                f"{describe_case(company, ukraine)} it gives {outcome}, expected {target}.",
            )
        unresolved = unresolved or (company, ukraine)

    if unresolved:
        return DomainVerdict(
            "REVIEW",
            "Equivalence cannot be established: the result depends on unrecognised conditions "
            f"when {describe_case(*unresolved)}.",
        )
    return DomainVerdict("PASS", "Domain is logically equivalent to active companies with country code UA.")


def describe_case(company, ukraine):
    return f"is_company={company} and country code UA={ukraine}"


def parse_domain(domain_text):
    """Return (formula, number_of_unknown_conditions) for a domain in prefix notation."""
    text = "[]" if domain_text in (None, False, "") else domain_text
    if isinstance(text, str):
        try:
            tokens = ast.literal_eval(text)
        except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError) as error:
            raise UnsupportedDomain("not a plain literal (dynamic expressions are not supported)") from error
    else:
        tokens = text
    if not isinstance(tokens, (list, tuple)):
        raise UnsupportedDomain("the domain is not a list")

    counter = [0]
    stack = []
    # Prefix notation is read right to left, so operands are on the stack when an operator arrives.
    for token in reversed(tokens):
        if isinstance(token, str):
            if token == "!":
                if not stack:
                    raise UnsupportedDomain("'!' has no operand")
                stack.append(("not", stack.pop()))
            elif token in ("&", "|"):
                if len(stack) < 2:
                    raise UnsupportedDomain(f"'{token}' needs two operands")
                left, right = stack.pop(), stack.pop()
                stack.append(("and" if token == "&" else "or", left, right))
            else:
                raise UnsupportedDomain(f"unknown logical operator {token!r}")
        else:
            stack.append(_condition_node(token, counter))

    if not stack:
        return ("const", True), 0
    formula = stack.pop()
    while stack:
        # Odoo joins top-level conditions with an implicit AND.
        formula = ("and", formula, stack.pop())
    return formula, counter[0]


def evaluate(node, env, unknown):
    kind = node[0]
    if kind == "const":
        return node[1]
    if kind == "company":
        return env["company"]
    if kind == "ukraine":
        return env["ukraine"]
    if kind == "unknown":
        return unknown[node[1]]
    if kind == "not":
        return not evaluate(node[1], env, unknown)
    left = evaluate(node[1], env, unknown)
    right = evaluate(node[2], env, unknown)
    return (left and right) if kind == "and" else (left or right)


def _condition_node(token, counter):
    if not isinstance(token, (list, tuple)) or len(token) != 3:
        raise UnsupportedDomain("a condition must be a (field, operator, value) triple")
    field, operator, value = token
    # Odoo's TRUE_LEAF (1, '=', 1) and FALSE_LEAF (0, '=', 1).
    if isinstance(field, int) and not isinstance(field, bool) and field in (0, 1) and operator == "=" and value == 1:
        return ("const", bool(field))
    known = None
    if isinstance(field, str) and isinstance(operator, str):
        known = _known_condition(field, operator, value)
    if known is not None:
        return known
    index = counter[0]
    counter[0] += 1
    return ("unknown", index)


def _known_condition(field, operator, value):
    if field == "active":
        # Searches already return only active records, so this condition is always true there.
        if (operator == "=" and _flag(value) is True) or (operator == "!=" and _flag(value) is False):
            return ("const", True)
        return None

    if field == "is_company" and operator in ("=", "!="):
        flag = _flag(value)
        if flag is None:
            return None
        positive = flag if operator == "=" else not flag
        return ("company",) if positive else ("not", ("company",))

    if field == "country_id.code":
        if operator in ("=", "!=") and value == "UA":
            node = ("ukraine",)
        elif operator in ("in", "not in") and isinstance(value, (list, tuple)) and list(value) == ["UA"]:
            node = ("ukraine",)
        else:
            return None
        return node if operator in ("=", "in") else ("not", node)

    return None


def _flag(value):
    """Return the boolean meaning of a flag value, or None if it is not a boolean-like value."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    return None
