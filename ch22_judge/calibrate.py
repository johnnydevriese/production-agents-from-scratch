"""Calibration — a judge you haven't checked against humans is a vibe.

A judge's score means nothing until you've shown it agrees with the humans whose
judgment it stands in for. Raw agreement is a trap: if 80% of reasons are "good,"
two raters guessing in that same 80/20 split agree 68% of the time
(0.8² + 0.2²) having learned nothing. Cohen's kappa corrects for exactly that
chance agreement.

The workflow: two humans grade a 50–100 sample against the *same* rubric (two, so
you also get a human–human kappa — your ceiling), run the judge on the same
sample, compute kappa, and iterate the *rubric and prompt* until judge–human kappa
approaches human–human kappa. Demanding more than the human ceiling is demanding
the judge be more consistent than the people it imitates.
"""

from __future__ import annotations

from sklearn.metrics import cohen_kappa_score


def calibrate(human_grades: list[int], judge_grades: list[int]) -> float:
    """Chance-corrected agreement between the judge and the human gold labels.

    weights="quadratic" → a 4-vs-5 disagreement counts far less than a 1-vs-5.
    The grades are ordinal, so they deserve ordinal credit; plain (unweighted)
    kappa would treat every disagreement as equally wrong.
    """
    if len(human_grades) != len(judge_grades):
        raise ValueError("graded sets must be aligned 1:1")
    return float(cohen_kappa_score(human_grades, judge_grades, weights="quadratic"))
