"""The coverage matrix: forcing the hard cells to exist.

Convenience-sampling always overfits to the happy path — the easy-to-reach cases
are systematically the easy ones. The cure is to write down the dimensions along
which invoices vary, take their cross-product, and demand a case in every cell
that can occur. The matrix makes the *gaps* visible, and the gaps are where
production breaks you.

Coverage is **cells filled, not rows counted**: a suite with 30 cases across every
cell tells you more than 1,000 piled into the happy-path corner. This module
reports `covered_cells / total_cells` and the exact `gaps`, so "we have lots of
cases" becomes the honest "we have lots of cases in two of six columns."
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from itertools import product

from pydantic import BaseModel

from .cases import EvalCase

Cell = tuple[str, ...]


class Dimension(BaseModel):
    name: str
    values: tuple[str, ...]


class CellCount(BaseModel):
    cell: tuple[str, ...]
    count: int


class CoverageReport(BaseModel):
    total_cells: int
    covered_cells: int
    gaps: list[tuple[str, ...]]
    counts: list[CellCount]

    @property
    def fraction_covered(self) -> float:
        return self.covered_cells / self.total_cells if self.total_cells else 0.0


# The autopilot's first-cut matrix (the chapter draws the 3×2 slice). A real matrix
# adds amount band, budget, vendor resolution, document quality, adversarial — the
# principle is unchanged: enumerate deliberately, fill every reachable cell.
PO_STATUS = Dimension(name="po_status", values=("matched", "mismatch", "none"))
CURRENCY = Dimension(name="currency", values=("USD", "non-USD"))
AUTOPILOT_DIMENSIONS: tuple[Dimension, ...] = (PO_STATUS, CURRENCY)


def full_grid(dimensions: Sequence[Dimension]) -> list[Cell]:
    return [tuple(combo) for combo in product(*(d.values for d in dimensions))]


def build_report(
    observed: Sequence[Cell], *, dimensions: Sequence[Dimension]
) -> CoverageReport:
    grid = full_grid(dimensions)
    valid = set(grid)
    tally: Counter[Cell] = Counter()
    for cell in observed:
        if cell not in valid:
            names = [d.name for d in dimensions]
            raise ValueError(f"cell {cell!r} is not in the grid for {names}")
        tally[cell] += 1
    covered = sum(1 for cell in grid if tally[cell] > 0)
    gaps = [cell for cell in grid if tally[cell] == 0]
    counts = [CellCount(cell=cell, count=tally[cell]) for cell in grid]
    return CoverageReport(
        total_cells=len(grid), covered_cells=covered, gaps=gaps, counts=counts
    )


def cell_of(case: EvalCase, *, dimensions: Sequence[Dimension]) -> Cell:
    try:
        return tuple(case.coverage[d.name] for d in dimensions)
    except KeyError as e:
        raise ValueError(f"case {case.id!r} is missing a coverage tag: {e}") from e


def report_for_cases(
    cases: Sequence[EvalCase], *, dimensions: Sequence[Dimension]
) -> CoverageReport:
    return build_report(
        [cell_of(case, dimensions=dimensions) for case in cases], dimensions=dimensions
    )
