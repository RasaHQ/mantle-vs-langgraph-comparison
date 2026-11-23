"""Build the comparison table from everything under results/.

    python harness/compare.py [results_dir]   # prints the tables, writes <results_dir>/README.md

Every batch of a setup (results/<setup>/<timestamp>/) is pooled. Definitions:

- Passing run: the judge passed every criterion and every assertion passed
  (``eval_passed`` in the run's JSON).
- Passing scenario: more than half of its runs passed (2 of 3, 5 of 9).
- Cost: ``engine_tokens.cost``, the agent's own LLM spend for one conversation.
  The simulated user and the judge are not included.
- Cost per conversation: mean over runs.
- Head-to-head cost compares the two setups on the same scenarios: all runs on
  every scenario, and passing runs on the scenarios both setups passed.
- Turn time: wall time from sending a user message to receiving the agent's reply.
"""

from __future__ import annotations

import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

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
    turn_times_s: list[float]


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


@dataclass
class SetupResults:
    batches: list[str]
    scenarios: dict[str, Scenario]
    per_batch: list[dict[str, Scenario]]

    @property
    def runs(self) -> list[Run]:
        return [r for s in self.scenarios.values() for r in s.runs]


def load_run(path: Path) -> Run:
    data = json.loads(path.read_text(encoding="utf-8"))
    cost = (data.get("engine_tokens") or {}).get("cost")
    turns = ((data.get("latency") or {}).get("per_turn")) or []
    return Run(
        passed=bool(data.get("eval_passed")),
        cost=float(cost) if cost is not None else None,
        harness_error=bool(data.get("error_is_harness")),
        turn_times_s=[t["turn_latency_ms"] / 1000 for t in turns if t.get("turn_latency_ms")],
    )


def load_setup(setup_dir: Path) -> Optional[SetupResults]:
    batches = sorted(d for d in setup_dir.iterdir() if d.is_dir()) if setup_dir.is_dir() else []
    if not batches:
        return None
    scenarios: dict[str, Scenario] = {}
    per_batch: list[dict[str, Scenario]] = []
    for batch in batches:
        batch_scenarios: dict[str, Scenario] = {}
        for path in sorted(batch.glob("*/run_*.json")):
            run = load_run(path)
            batch_scenarios.setdefault(path.parent.name, Scenario()).runs.append(run)
            scenarios.setdefault(path.parent.name, Scenario()).runs.append(run)
        per_batch.append(batch_scenarios)
    return SetupResults([b.name for b in batches], scenarios, per_batch)


def mean(values: list[float]) -> Optional[float]:
    return statistics.fmean(values) if values else None


def money(value: Optional[float]) -> str:
    return "—" if value is None else f"${value:.4f}"


def percentile(values: list[float], q: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[int(q * (len(ordered) - 1))]


def pooled_cost(results: SetupResults, names: list[str], passing_only: bool) -> Optional[float]:
    return mean([c for n in names for c in results.scenarios[n].costs(passing_only)])


def main_table(loaded: dict[str, SetupResults], shared: list[str]) -> list[str]:
    keys = list(loaded)
    lines = ["| | " + " | ".join(SETUPS[k] for k in keys) + " |", "|---|" + "---:|" * len(keys)]

    def row(title: str, cells: list[str]) -> None:
        lines.append(f"| {title} | " + " | ".join(cells) + " |")

    def scen(k: str) -> dict[str, Scenario]:
        return {n: loaded[k].scenarios[n] for n in shared}

    row("Scenarios passing", [f"{sum(s.passed for s in scen(k).values())}/{len(shared)}" for k in keys])
    row(
        "Run pass rate",
        [
            f"{sum(s.passing_runs for s in scen(k).values()) / sum(len(s.runs) for s in scen(k).values()):.0%} "
            f"({sum(s.passing_runs for s in scen(k).values())}/{sum(len(s.runs) for s in scen(k).values())})"
            for k in keys
        ],
    )
    row(
        "Scenarios passing per batch",
        [", ".join(str(sum(b[n].passed for n in shared if n in b)) for b in loaded[k].per_batch) for k in keys],
    )
    row("Cost per conversation, all runs", [money(pooled_cost(loaded[k], shared, False)) for k in keys])
    row("Cost per conversation, passing runs¹", [money(pooled_cost(loaded[k], shared, True)) for k in keys])
    for title, q in (("Turn time p50", 0.5), ("Turn time p90", 0.9)):
        cells = []
        for k in keys:
            value = percentile([t for s in scen(k).values() for r in s.runs for t in r.turn_times_s], q)
            cells.append("—" if value is None else f"{value:.1f}s")
        row(title, cells)
    row("Harness errors", [str(sum(r.harness_error for s in scen(k).values() for r in s.runs)) for k in keys])
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
        all_ratio = ratio(pooled_cost(base, shared, False), pooled_cost(other, shared, False))
        both = [n for n in shared if base.scenarios[n].passed and other.scenarios[n].passed]
        pass_ratio = ratio(pooled_cost(base, both, True), pooled_cost(other, both, True))
        lines.append(f"| vs {SETUPS[key]} | {all_ratio} | {pass_ratio} ({len(both)} scenarios) |")
    return lines


def ratio(a: Optional[float], b: Optional[float]) -> str:
    return f"{a / b:.2f}×" if a and b else "—"


def scenario_table(loaded: dict[str, SetupResults], shared: list[str]) -> list[str]:
    keys = list(loaded)
    lines = [
        "| Scenario | " + " | ".join(f"{SETUPS[k]} passing runs" for k in keys) + " |",
        "|---|" + ":-:|" * len(keys),
    ]
    for name in shared:
        cells = []
        for k in keys:
            s = loaded[k].scenarios[name]
            mark = "✓" if s.passed else "✗"
            cells.append(f"{mark} {s.passing_runs}/{len(s.runs)}")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return lines


def main() -> None:
    global RESULTS_DIR
    if len(sys.argv) > 1:
        RESULTS_DIR = Path(sys.argv[1]).resolve()
    loaded = {k: r for k in SETUPS if (r := load_setup(RESULTS_DIR / k)) is not None}
    if not loaded:
        raise SystemExit("No results under results/. Run harness/run.py first.")
    shared = sorted(set.intersection(*(set(r.scenarios) for r in loaded.values())))
    dropped = sorted(set.union(*(set(r.scenarios) for r in loaded.values())) - set(shared))

    out = ["# Results", ""]
    out.append(
        "Generated by `harness/compare.py` from the per-run JSON files in this folder. "
        f"{len(shared)} scenarios."
    )
    out.append("")
    out.append("| Setup | Batches | Runs per scenario |")
    out.append("|---|---|---:|")
    for k, r in loaded.items():
        runs = {len(r.scenarios[n].runs) for n in shared}
        out.append(f"| {SETUPS[k]} | {', '.join(f'`{b}`' for b in r.batches)} | {'/'.join(map(str, sorted(runs)))} |")
    if dropped:
        out += ["", f"Left out because not every setup ran them: {', '.join(dropped)}."]
    out += ["", "## Summary", ""] + main_table(loaded, shared)
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
    out += ["", "## Per scenario", ""] + scenario_table(loaded, shared)
    out += ["", "## Definitions", "", __doc__.split("Definitions:", 1)[1].strip(), ""]

    text = "\n".join(out)
    (RESULTS_DIR / "README.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"\nWrote {RESULTS_DIR / 'README.md'}")


if __name__ == "__main__":
    main()
