"""Build the comparison table from everything under results/.

    python harness/compare.py [results_dir]   # prints the tables, writes <results_dir>/README.md

A "run" is one pass over every scenario: one conversation per scenario. Each
folder results/<setup>/<timestamp>/ holds 3 runs (run_1, run_2, run_3 of each
scenario), so three folders give 9 runs. Every metric is computed for each run
on its own; the table shows the mean and the sample standard deviation (±)
across runs.

Definitions:

- Passing conversation: the judge passed every criterion and every assertion
  passed (``eval_passed`` in the conversation's JSON).
- Scenarios passed: how many of the scenarios' conversations passed in one run.
- Cost: ``engine_tokens.cost``, the agent's own LLM spend for one conversation.
  The simulated user and the judge are not included.
- Cost per conversation: in each run, the mean cost of its conversations (all,
  or only the passing ones).
- Head-to-head: in each run, Mantle's cost per conversation divided by the other
  setup's, on the same scenarios: all of them, or only those both passed in that
  run. Runs are paired in the order they ran (first with first).
- Passed in most runs: scenarios that passed in more than half of all runs.
- Timeouts: "Conversations ended by a timeout" have a timeout as their error
  (the agent never answered a turn after 3 attempts, or the conversation hit its
  time limit). "Turns resent after a timeout" counts user messages the harness
  sent again because no reply came within the turn timeout. "Agent LLM call
  timeouts" are the agent's own OpenAI calls that timed out, from its server log.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from dataclasses import dataclass
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
class Conversation:
    passed: bool
    cost: Optional[float]
    prompt_tokens: int
    cached_tokens: int
    harness_error: bool
    timed_out: bool


Run = dict[str, Conversation]  # scenario name -> its conversation in this run


@dataclass
class SetupResults:
    folders: list[str]
    runs: list[Run]  # in the order they ran
    folder_info: list[dict]  # run_info.json of each folder


def load_conversation(data: dict) -> Conversation:
    tokens = data.get("engine_tokens") or {}
    cost = tokens.get("cost")
    return Conversation(
        passed=bool(data.get("eval_passed")),
        cost=float(cost) if cost is not None else None,
        prompt_tokens=int(tokens.get("prompt") or 0),
        cached_tokens=int(tokens.get("cached") or 0),
        harness_error=bool(data.get("error_is_harness")),
        timed_out=bool(re.search(r"timeout|timed out", data.get("error") or "", re.IGNORECASE)),
    )


def load_setup(setup_dir: Path) -> Optional[SetupResults]:
    folders = sorted(d for d in setup_dir.iterdir() if d.is_dir()) if setup_dir.is_dir() else []
    if not folders:
        return None
    runs: list[Run] = []
    info: list[dict] = []
    for folder in folders:
        by_index: dict[int, Run] = {}
        for path in sorted(folder.glob("*/run_*.json")):
            index = int(path.stem.split("_")[1])
            by_index.setdefault(index, {})[path.parent.name] = load_conversation(
                json.loads(path.read_text(encoding="utf-8"))
            )
        runs += [by_index[i] for i in sorted(by_index)]
        info_path = folder / "run_info.json"
        info.append(json.loads(info_path.read_text(encoding="utf-8")) if info_path.is_file() else {})
    return SetupResults([f.name for f in folders], runs, info)


# --- metrics for one run -----------------------------------------------------


def scenarios_passed(run: Run, names: list[str]) -> float:
    return sum(run[n].passed for n in names if n in run)


def mean_cost(run: Run, names: list[str], passing_only: bool) -> Optional[float]:
    costs = [
        run[n].cost
        for n in names
        if n in run and run[n].cost is not None and (run[n].passed or not passing_only)
    ]
    return statistics.fmean(costs) if costs else None


def cache_share(run: Run, names: list[str]) -> Optional[float]:
    prompt = sum(run[n].prompt_tokens for n in names if n in run)
    return sum(run[n].cached_tokens for n in names if n in run) / prompt if prompt else None


def cost_ratio(a: Run, b: Run, names: list[str], passing_only: bool) -> Optional[float]:
    if passing_only:
        names = [n for n in names if n in a and n in b and a[n].passed and b[n].passed]
    ca, cb = mean_cost(a, names, passing_only), mean_cost(b, names, passing_only)
    return ca / cb if ca and cb else None


# --- formatting --------------------------------------------------------------


def mean_sd(values: list[Optional[float]]) -> tuple[Optional[float], Optional[float]]:
    present = [v for v in values if v is not None]
    if not present:
        return None, None
    return statistics.fmean(present), (statistics.stdev(present) if len(present) > 1 else None)


def show(values: list[Optional[float]], fmt) -> str:
    mean, sd = mean_sd(values)
    if mean is None:
        return "—"
    return fmt(mean) + (f" ± {fmt(sd)}" if sd is not None else "")


def money(v: float) -> str:
    return f"${v:.4f}"


def ratio(v: float) -> str:
    return f"{v:.2f}×"


# --- tables ------------------------------------------------------------------


def summary_table(loaded: dict[str, SetupResults], shared: list[str]) -> list[str]:
    keys = list(loaded)
    n = len(shared)
    lines = ["| Metric | " + " | ".join(SETUPS[k] for k in keys) + " |", "|---|" + "---:|" * len(keys)]

    def row(title: str, cells: list[str]) -> None:
        lines.append(f"| {title} | " + " | ".join(cells) + " |")

    def passed_cell(k: str) -> str:
        values = [scenarios_passed(r, shared) for r in loaded[k].runs]
        mean, sd = mean_sd(values)
        return f"{mean:.1f}/{n} ± {sd:.1f} ({mean / n:.1%})" if sd is not None else f"{mean:.1f}/{n} ({mean / n:.1%})"

    row("Runs", [str(len(loaded[k].runs)) for k in keys])
    row("Scenarios passed per run", [passed_cell(k) for k in keys])
    row(
        "Cost per conversation, all",
        [show([mean_cost(r, shared, False) for r in loaded[k].runs], money) for k in keys],
    )
    row(
        "Cost per conversation, passing only¹",
        [show([mean_cost(r, shared, True) for r in loaded[k].runs], money) for k in keys],
    )

    row(
        "Agent prompt tokens served from cache²",
        [show([cache_share(r, shared) for r in loaded[k].runs], lambda v: f"{v:.1%}") for k in keys],
    )

    def passed_in_most(k: str) -> str:
        runs = loaded[k].runs
        count = sum(sum(r[s].passed for r in runs if s in r) * 2 > len(runs) for s in shared)
        return f"{count}/{n}"

    row("Scenarios passed in most runs", [passed_in_most(k) for k in keys])

    def total(values: list[Optional[int]]) -> str:
        present = [v for v in values if v is not None]
        return str(sum(present)) if present else "—"

    row(
        "Conversations ended by a timeout",
        [total([sum(r[s].timed_out for s in shared if s in r) for r in loaded[k].runs]) for k in keys],
    )
    for title, field_name in (
        ("Turns resent after a timeout", "turn_retries"),
        ("Agent LLM call timeouts", "agent_llm_timeouts"),
    ):
        row(title, [total([(i.get("timeouts") or {}).get(field_name) for i in loaded[k].folder_info]) for k in keys])
    row(
        "Harness errors",
        [total([sum(r[s].harness_error for s in shared if s in r) for r in loaded[k].runs]) for k in keys],
    )
    return lines


def head_to_head(loaded: dict[str, SetupResults], shared: list[str]) -> list[str]:
    if BASELINE not in loaded:
        return []
    base = loaded[BASELINE]
    lines = [
        f"| {SETUPS[BASELINE]} cost ÷ other setup's cost | All {len(shared)} scenarios | "
        "Scenarios both passed in that run |",
        "|---|---:|---:|",
    ]
    for key, other in loaded.items():
        if key == BASELINE:
            continue
        pairs = list(zip(base.runs, other.runs))
        cells = [show([cost_ratio(a, b, shared, p) for a, b in pairs], ratio) for p in (False, True)]
        lines.append(f"| vs {SETUPS[key]} ({len(pairs)} paired runs) | {cells[0]} | {cells[1]} |")
    return lines


def scenario_table(loaded: dict[str, SetupResults], shared: list[str]) -> list[str]:
    keys = list(loaded)
    lines = [
        "| Scenario | " + " | ".join(f"{SETUPS[k]}, runs passed" for k in keys) + " |",
        "|---|" + ":-:|" * len(keys),
    ]
    for name in shared:
        cells = []
        for k in keys:
            runs = [r for r in loaded[k].runs if name in r]
            passed = sum(r[name].passed for r in runs)
            cells.append(f"{passed}/{len(runs)}")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return lines


def main() -> None:
    global RESULTS_DIR
    if len(sys.argv) > 1:
        RESULTS_DIR = Path(sys.argv[1]).resolve()
    loaded = {k: r for k in SETUPS if (r := load_setup(RESULTS_DIR / k)) is not None}
    if not loaded:
        raise SystemExit("No results under results/. Run harness/run.py first.")
    names = [set().union(*r.runs) for r in loaded.values()]
    shared = sorted(set.intersection(*names))
    dropped = sorted(set.union(*names) - set(shared))

    out = ["# Results", ""]
    out.append(
        f"Generated by `harness/compare.py` from the per-conversation JSON files in this folder. "
        f"{len(shared)} scenarios. A run is one conversation per scenario. Each metric is computed "
        "per run; the table shows the mean ± the standard deviation across runs."
    )
    out += ["", "| Setup | Result folders |", "|---|---|"]
    for k, r in loaded.items():
        out.append(f"| {SETUPS[k]} | {', '.join(f'`{f}`' for f in r.folders)} |")
    if dropped:
        out += ["", f"Left out because not every setup ran them: {', '.join(dropped)}."]
    out += ["", "## Summary", ""] + summary_table(loaded, shared)
    out += [
        "",
        "¹ Each setup's own passing conversations, so the scenario mix differs between columns. "
        "A setup that passes more of the long scenarios pays for them here. "
        "Use the head-to-head table to compare cost.",
        "",
        "² OpenAI bills cached prompt tokens at a tenth of the input price. How much it caches "
        "depends on OpenAI's side and varies between runs, so it moves the cost even when the "
        "agent uses the same tokens.",
    ]
    h2h = head_to_head(loaded, shared)
    if h2h:
        out += ["", "## Cost head-to-head", ""] + h2h
        out += [
            "",
            "Below 1 means Mantle is cheaper. The second column only counts scenarios both "
            "setups passed in that run, so both are measured on the same conversations.",
        ]
    out += ["", "## Per scenario", ""] + scenario_table(loaded, shared)
    out += ["", "## Definitions", "", __doc__.split("Definitions:", 1)[1].strip(), ""]

    text = "\n".join(out)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "README.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"\nWrote {RESULTS_DIR / 'README.md'}")


if __name__ == "__main__":
    main()
