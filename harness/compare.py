"""Build the comparison table from everything under results/.

    python harness/compare.py [results_dir]   # prints the tables, writes <results_dir>/README.md

Each folder results/<setup>/<timestamp>/ is one set: every scenario run 3 times.
Definitions:

- Passing run: the judge passed every criterion and every assertion passed
  (``eval_passed`` in the run's JSON).
- Passing scenario: more than half of its runs passed (2 of 3 within a set,
  5 of 9 over three sets).
- Cost: ``engine_tokens.cost``, the agent's own LLM spend for one conversation.
  The simulated user and the judge are not included.
- Cost per conversation: mean over runs.
- Head-to-head cost compares Mantle with another setup on the same scenarios:
  all runs on every scenario, and passing runs on the scenarios both setups passed.
- ± is the sample standard deviation of the metric across sets: the metric is
  computed for each set on its own, and the spread of those values is reported.
  For the head-to-head, sets are paired in the order they ran (first with first).
"""

from __future__ import annotations

import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parents[1]
RESULTS_DIR = REPO / "results"
SETUPS = {
    "mantle": "Mantle",
    "lg": "LangGraph",
    "lg-high": "LangGraph, reasoning high",
}
BASELINE = "mantle"


@dataclass
class Run:
    passed: bool
    cost: Optional[float]
    harness_error: bool


@dataclass
class Scenario:
    runs: list[Run] = field(default_factory=list)

    @property
    def passing_runs(self) -> int:
        return sum(r.passed for r in self.runs)

    @property
    def passed(self) -> bool:
        return self.passing_runs * 2 > len(self.runs)

    def costs(self, passing_only: bool) -> list[float]:
        return [r.cost for r in self.runs if r.cost is not None and (r.passed or not passing_only)]


Results = dict[str, Scenario]  # scenario name -> its runs


@dataclass
class SetupResults:
    set_names: list[str]
    sets: list[Results]  # one entry per set, in the order they ran
    pooled: Results  # all sets together


def load_run(path: Path) -> Run:
    data = json.loads(path.read_text(encoding="utf-8"))
    cost = (data.get("engine_tokens") or {}).get("cost")
    return Run(
        passed=bool(data.get("eval_passed")),
        cost=float(cost) if cost is not None else None,
        harness_error=bool(data.get("error_is_harness")),
    )


def load_setup(setup_dir: Path) -> Optional[SetupResults]:
    set_dirs = sorted(d for d in setup_dir.iterdir() if d.is_dir()) if setup_dir.is_dir() else []
    if not set_dirs:
        return None
    sets: list[Results] = []
    pooled: Results = {}
    for set_dir in set_dirs:
        one_set: Results = {}
        for path in sorted(set_dir.glob("*/run_*.json")):
            run = load_run(path)
            one_set.setdefault(path.parent.name, Scenario()).runs.append(run)
            pooled.setdefault(path.parent.name, Scenario()).runs.append(run)
        sets.append(one_set)
    return SetupResults([d.name for d in set_dirs], sets, pooled)


# --- metrics on one group of results ------------------------------------------


def scenarios_passing(results: Results, names: list[str]) -> float:
    return sum(results[n].passed for n in names)


def run_pass_rate(results: Results, names: list[str]) -> Optional[float]:
    runs = [r for n in names for r in results[n].runs]
    return sum(r.passed for r in runs) / len(runs) if runs else None


def mean_cost(results: Results, names: list[str], passing_only: bool) -> Optional[float]:
    costs = [c for n in names for c in results[n].costs(passing_only)]
    return statistics.fmean(costs) if costs else None


def both_passed(a: Results, b: Results, names: list[str]) -> list[str]:
    return [n for n in names if a[n].passed and b[n].passed]


def cost_ratio(a: Results, b: Results, names: list[str], passing_only: bool) -> Optional[float]:
    if passing_only:
        names = both_passed(a, b, names)
    ca, cb = mean_cost(a, names, passing_only), mean_cost(b, names, passing_only)
    return ca / cb if ca and cb else None


# --- formatting ---------------------------------------------------------------


def spread(values: list[Optional[float]]) -> tuple[Optional[float], Optional[float]]:
    """Mean and sample standard deviation; SD needs at least two values."""
    present = [v for v in values if v is not None]
    if not present:
        return None, None
    sd = statistics.stdev(present) if len(present) > 1 else None
    return statistics.fmean(present), sd


def fmt(value: Optional[float], kind: str) -> str:
    if value is None:
        return "—"
    if kind == "money":
        return f"${value:.4f}"
    if kind == "pct":
        return f"{value * 100:.1f}%"
    if kind == "ratio":
        return f"{value:.2f}×"
    return f"{value:.1f}"


def with_sd(pooled: Optional[float], per_set: list[Optional[float]], kind: str) -> str:
    _, sd = spread(per_set)
    text = fmt(pooled, kind)
    if sd is not None:
        sd_text = f"{sd * 100:.1f} pp" if kind == "pct" else fmt(sd, kind)
        text += f" ± {sd_text}"
    return text


# --- tables -------------------------------------------------------------------


def summary_table(loaded: dict[str, SetupResults], shared: list[str]) -> list[str]:
    keys = list(loaded)
    lines = ["| Metric | " + " | ".join(SETUPS[k] for k in keys) + " |", "|---|" + "---:|" * len(keys)]

    def row(title: str, cells: list[str]) -> None:
        lines.append(f"| {title} | " + " | ".join(cells) + " |")

    def per_set(k: str, metric: Callable[[Results], Optional[float]]) -> list[Optional[float]]:
        return [metric(s) for s in loaded[k].sets]

    n = len(shared)
    row(
        "Scenarios passing, all runs pooled",
        [f"{int(scenarios_passing(loaded[k].pooled, shared))}/{n}" for k in keys],
    )
    cells = []
    for k in keys:
        values = per_set(k, lambda s: scenarios_passing(s, shared))
        mean, sd = spread(values)
        listed = ", ".join(str(int(v)) for v in values)
        cells.append(f"{mean:.1f}/{n}" + (f" ± {sd:.1f}" if sd is not None else "") + f" ({listed})")
    row("Scenarios passing per set", cells)
    row(
        "Run pass rate",
        [
            with_sd(run_pass_rate(loaded[k].pooled, shared), per_set(k, lambda s: run_pass_rate(s, shared)), "pct")
            for k in keys
        ],
    )
    for title, passing_only in (("Cost per conversation, all runs", False), ("Cost per conversation, passing runs¹", True)):
        row(
            title,
            [
                with_sd(
                    mean_cost(loaded[k].pooled, shared, passing_only),
                    per_set(k, lambda s, p=passing_only: mean_cost(s, shared, p)),
                    "money",
                )
                for k in keys
            ],
        )
    row(
        "Runs",
        [str(sum(len(loaded[k].pooled[n].runs) for n in shared)) for k in keys],
    )
    row(
        "Harness errors",
        [str(sum(r.harness_error for n in shared for r in loaded[k].pooled[n].runs)) for k in keys],
    )
    return lines


def head_to_head(loaded: dict[str, SetupResults], shared: list[str]) -> list[str]:
    if BASELINE not in loaded:
        return []
    base = loaded[BASELINE]
    lines = [
        f"| {SETUPS[BASELINE]} cost ÷ other setup's cost | All runs, all {len(shared)} scenarios | "
        "Passing runs, scenarios both passed |",
        "|---|---:|---:|",
    ]
    for key, other in loaded.items():
        if key == BASELINE:
            continue
        pairs = list(zip(base.sets, other.sets))
        cells = []
        for passing_only in (False, True):
            pooled = cost_ratio(base.pooled, other.pooled, shared, passing_only)
            per_set = [cost_ratio(a, b, shared, passing_only) for a, b in pairs]
            cells.append(with_sd(pooled, per_set, "ratio"))
        n_both = len(both_passed(base.pooled, other.pooled, shared))
        lines.append(f"| vs {SETUPS[key]} | {cells[0]} | {cells[1]} ({n_both} scenarios) |")
    return lines


def scenario_table(loaded: dict[str, SetupResults], shared: list[str]) -> list[str]:
    keys = list(loaded)
    lines = [
        "| Scenario | " + " | ".join(SETUPS[k] for k in keys) + " |",
        "|---|" + ":-:|" * len(keys),
    ]
    for name in shared:
        cells = []
        for k in keys:
            s = loaded[k].pooled[name]
            mark = "✓" if s.passed else "✗"
            per_set = ", ".join(str(one[name].passing_runs) for one in loaded[k].sets if name in one)
            cells.append(f"{mark} {s.passing_runs}/{len(s.runs)} ({per_set})")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return lines


def main() -> None:
    global RESULTS_DIR
    if len(sys.argv) > 1:
        RESULTS_DIR = Path(sys.argv[1]).resolve()
    loaded = {k: r for k in SETUPS if (r := load_setup(RESULTS_DIR / k)) is not None}
    if not loaded:
        raise SystemExit("No results under results/. Run harness/run.py first.")
    shared = sorted(set.intersection(*(set(r.pooled) for r in loaded.values())))
    dropped = sorted(set.union(*(set(r.pooled) for r in loaded.values())) - set(shared))

    out = ["# Results", ""]
    out.append(
        f"Generated by `harness/compare.py` from the per-run JSON files in this folder. {len(shared)} scenarios. "
        "Each set runs every scenario 3 times."
    )
    out += ["", "| Setup | Sets |", "|---|---|"]
    for k, r in loaded.items():
        out.append(f"| {SETUPS[k]} | {', '.join(f'`{name}`' for name in r.set_names)} |")
    if dropped:
        out += ["", f"Left out because not every setup ran them: {', '.join(dropped)}."]
    out += ["", "## Summary", ""]
    out.append(
        "Values pool every run of a setup. ± is the standard deviation across sets: "
        "how much the metric moves from one set of 3 runs per scenario to the next."
    )
    out += [""] + summary_table(loaded, shared)
    out += [
        "",
        "¹ Each setup's own passing runs, so the scenario mix differs between columns. "
        "A setup that passes more of the long scenarios pays for them here. "
        "Use the head-to-head table to compare cost.",
    ]
    h2h = head_to_head(loaded, shared)
    if h2h:
        out += ["", "## Cost head-to-head", ""] + h2h
        out += [
            "",
            "Below 1 means Mantle is cheaper. The passing-runs column only counts scenarios "
            "both setups passed, so both are measured on the same conversations.",
        ]
    out += ["", "## Per scenario", "", "Passing runs over all sets, then per set in brackets.", ""]
    out += scenario_table(loaded, shared)
    out += ["", "## Definitions", "", __doc__.split("Definitions:", 1)[1].strip(), ""]

    text = "\n".join(out)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "README.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"\nWrote {RESULTS_DIR / 'README.md'}")


if __name__ == "__main__":
    main()
