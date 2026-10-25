"""Explicit transitions; failures and cancellation are legal from active states."""

STATES = frozenset(
    """CREATED ANALYZING PLANNING AWAITING_PLAN_APPROVAL APPROVED QUEUED
EXECUTING TESTING REVIEWING SECURITY_CHECKING REPAIRING VERIFIED READY_FOR_GIT
AWAITING_GIT_APPROVAL COMMITTING PUSHING CI_PENDING CI_RUNNING CI_FAILED READY_FOR_PR
AWAITING_MERGE_APPROVAL COMPLETED FAILED BLOCKED CANCELLED""".split()
)
TERMINAL = {"COMPLETED", "FAILED", "BLOCKED", "CANCELLED", "VERIFIED"}
EDGES = {
    "CREATED": {"ANALYZING"},
    "ANALYZING": {"PLANNING", "EXECUTING"},
    "PLANNING": {"AWAITING_PLAN_APPROVAL"},
    "AWAITING_PLAN_APPROVAL": {"APPROVED"},
    "APPROVED": {"QUEUED"},
    "QUEUED": {"ANALYZING", "EXECUTING"},
    "EXECUTING": {"TESTING"},
    "TESTING": {"REPAIRING", "REVIEWING", "VERIFIED"},
    "REPAIRING": {"EXECUTING"},
    "REVIEWING": {"SECURITY_CHECKING"},
    "SECURITY_CHECKING": {"VERIFIED"},
    "VERIFIED": {"READY_FOR_GIT"},
    "READY_FOR_GIT": {"AWAITING_GIT_APPROVAL"},
    "AWAITING_GIT_APPROVAL": {"COMMITTING"},
    "COMMITTING": {"PUSHING", "COMPLETED"},
    "PUSHING": {"CI_PENDING"},
    "CI_PENDING": {"CI_RUNNING"},
    "CI_RUNNING": {"CI_FAILED", "READY_FOR_PR"},
    "CI_FAILED": {"REPAIRING"},
    "READY_FOR_PR": {"COMPLETED"},
    # Autonomous merge is deliberately absent.
}


def validate(previous: str, target: str):
    if previous not in STATES or target not in STATES:
        raise ValueError("Unknown workflow state")
    if target in {"FAILED", "BLOCKED", "CANCELLED"} and previous not in TERMINAL:
        return
    if target not in EDGES.get(previous, set()):
        raise ValueError(f"Invalid workflow transition: {previous} -> {target}")
