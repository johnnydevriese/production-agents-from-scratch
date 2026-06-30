"""Discipline 4b — migrate models on purpose, not "change the string and pray".

A pinned model ID is a deprecation window, not permanence. When the provider retires
it, the successor is a *new function* from text to a distribution (Chapter 1): same
prompt, different behavior. So the candidate is treated as a new `AgentRelease` and
run through the same gates as any code change.

Step 1 is the one teams skip and the one that saves them: run the candidate AND the
incumbent against the *frozen* offline suite (Chapter 20) and diff case-by-case. A
money-path case that flips pass→fail is an instant stop — money movement gets no
benefit of the doubt. For the rest, the question "did it get *significantly* worse?"
is answered with McNemar on the paired outcomes (Chapter 21), not a vibe: one net
flip is noise; a consistent run of regressions is real.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from ch21_stats.compare import paired_eval_test


class CaseOutcome(BaseModel, frozen=True):
    """One eval case's result on one model — paired by `name` across the two runs."""

    name: str
    passed: bool
    is_money_path: bool = False  # a case that asserts on schedule_payment / GL posting


class MigrationDiff(BaseModel):
    """The behavioral diff between incumbent and candidate on the frozen suite."""

    regressions: list[str]  # cases that flipped pass → fail
    gains: list[str]  # cases that flipped fail → pass
    money_path_regressions: list[str]  # the subset of regressions on a money path
    mcnemar_p_value: float

    @property
    def significant(self) -> bool:
        return self.mcnemar_p_value < 0.05

    @property
    def safe_to_migrate(self) -> bool:
        """A migration that regresses a money path — or that is significantly worse
        overall — is not a migration. Otherwise the successor may ship."""
        if self.money_path_regressions:
            return False
        return not (self.significant and len(self.regressions) > len(self.gains))


def migration_diff(
    *, incumbent: Sequence[CaseOutcome], candidate: Sequence[CaseOutcome]
) -> MigrationDiff:
    """Diff two frozen-suite runs case-by-case. The runs must cover the identical
    cases (the suite is the fixed yardstick), so a mismatch is a setup error, raised."""
    by_name = {case.name: case for case in incumbent}
    if {c.name for c in candidate} != set(by_name):
        raise ValueError("candidate and incumbent must run the identical frozen suite")

    regressions: list[str] = []
    gains: list[str] = []
    money_path_regressions: list[str] = []
    for new in candidate:
        old = by_name[new.name]
        if old.passed and not new.passed:
            regressions.append(new.name)
            if new.is_money_path:
                money_path_regressions.append(new.name)
        elif not old.passed and new.passed:
            gains.append(new.name)

    if not regressions and not gains:
        p_value = 1.0  # nothing flipped — nothing to test
    else:
        p_value = paired_eval_test(
            pass_to_fail=len(regressions), fail_to_pass=len(gains)
        )
    return MigrationDiff(
        regressions=regressions,
        gains=gains,
        money_path_regressions=money_path_regressions,
        mcnemar_p_value=p_value,
    )
