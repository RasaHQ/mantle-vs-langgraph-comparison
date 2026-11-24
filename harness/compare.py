"""Build the comparison table from everything under results/.

    python harness/compare.py [results_dir]   # prints the tables, writes <results_dir>/README.md

A "run" is one pass over every scenario: one conversation per scenario. Each
folder results/<setup>/<timestamp>/ holds 3 runs (run_1, run_2, run_3 of each
scenario); more folders add more runs.

Definitions:

- Resolved conversation: the judge passed every criterion and every assertion
  passed (``eval_passed`` in the conversation's JSON).
- Cost: ``engine_tokens.cost``, the agent's own LLM spend for one conversation.
  The simulated user and the judge are not included.
- Reliably resolved scenario: a scenario resolved in every one of its runs.
- Total cost: the agent's cost summed over all of a setup's conversations,
  resolved or not.
- Cost per conversation = total cost / number of conversations.
- Cost per resolved conversation = total cost / conversations resolved.
- Cost per reliably resolved scenario (the headline) = (total cost / runs) /
  reliably resolved scenarios. Total cost / runs is what one run over all
  scenarios costs. A scenario resolved only in some runs adds cost but does not
  count.
- Scenarios resolved in at least k of the runs: how many scenarios the agent
  resolved at least k times. "All runs" is the headline's reliably resolved.
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
    "mantle": "Mantle (reasoning: none)",
    "lg": "LangGraph (reasoning: none)",
    "lg-high": "LangGraph (reasoning: high)",
}


@dataclass
class Conversation:
    passed: bool
    cost: Optional[float]
    prompt_tokens: int
    cached_tokens: int
    harness_error: bool
    timed_out: bool
    eval_cost: float = 0.0  # simulated customer + judge


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
        eval_cost=float((data.get("evaluation_tokens") or {}).get("cost") or 0.0),
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


def cache_share(run: Run, names: list[str]) -> Optional[float]:
    prompt = sum(run[n].prompt_tokens for n in names if n in run)
    return sum(run[n].cached_tokens for n in names if n in run) / prompt if prompt else None


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


def resolved_and_cost(results: SetupResults, names: list[str]) -> tuple[int, int, float]:
    """Returns (resolved conversations, all conversations, total cost)."""
    convs = [run[n] for run in results.runs for n in names if n in run]
    return (
        sum(c.passed for c in convs),
        len(convs),
        sum(c.cost for c in convs if c.cost is not None),
    )


def pass_k(results: SetupResults, names: list[str], k: int) -> int:
    """Scenarios that passed in at least *k* of their runs."""
    return sum(
        sum(run[n].passed for run in results.runs if n in run) >= k for n in names
    )


def reliable_cost(results: SetupResults, names: list[str]) -> tuple[int, Optional[float]]:
    """Returns (scenarios resolved in every run, cost per reliably resolved scenario)."""
    _, convs, cost = resolved_and_cost(results, names)
    solved = pass_k(results, names, len(results.runs))
    per_run = cost / convs * len(names) if convs else 0.0
    return solved, (per_run / solved if solved else None)


def headline_table(loaded: dict[str, SetupResults], shared: list[str]) -> list[str]:
    n = len(shared)
    lines = [
        "| Setup | Scenarios resolved in all runs | Cost per reliably resolved scenario |",
        "|---|---:|---:|",
    ]
    for k, r in loaded.items():
        solved, per = reliable_cost(r, shared)
        lines.append(
            f"| {SETUPS[k]} | {solved}/{n} ({solved / n:.1%}) | **{money(per) if per else '—'}** |"
        )
    return lines


def _table(loaded: dict[str, SetupResults], rows: list[tuple[str, list[str]]]) -> list[str]:
    keys = list(loaded)
    lines = ["| Metric | " + " | ".join(SETUPS[k] for k in keys) + " |", "|---|" + "---:|" * len(keys)]
    lines += [f"| {title} | " + " | ".join(cells) + " |" for title, cells in rows]
    return lines


def accuracy_table(loaded: dict[str, SetupResults], shared: list[str]) -> list[str]:
    keys = list(loaded)
    n = len(shared)
    runs = max(len(loaded[k].runs) for k in keys)
    rows = []
    for kk in sorted({runs, *range(1, min(3, runs))}, reverse=True):
        label = f"all {runs} runs" if kk == runs else f"at least {kk} of {runs} runs"
        cells = []
        for k in keys:
            m = pass_k(loaded[k], shared, kk)
            cells.append(f"{m}/{n} ({m / n:.1%})")
        rows.append((f"Scenarios resolved in {label}", cells))
    return _table(loaded, rows)


def cost_table(loaded: dict[str, SetupResults], shared: list[str]) -> list[str]:
    keys = list(loaded)
    stats = {k: resolved_and_cost(loaded[k], shared) for k in keys}
    reliable = {k: reliable_cost(loaded[k], shared)[1] for k in keys}
    rows = [
        ("**Cost per reliably resolved scenario**", [f"**{money(reliable[k])}**" if reliable[k] else "—" for k in keys]),
        (
            "Cost per resolved conversation",
            [money(stats[k][2] / stats[k][0]) if stats[k][0] else "—" for k in keys],
        ),
        ("Cost per conversation", [money(stats[k][2] / stats[k][1]) for k in keys]),
        (
            "Agent prompt tokens served from cache¹",
            [show([cache_share(r, shared) for r in loaded[k].runs], lambda v: f"{v:.1%}") for k in keys],
        ),
    ]
    return _table(loaded, rows)


def _minutes(info: dict) -> Optional[float]:
    from datetime import datetime

    try:
        start = datetime.fromisoformat(info["started"])
        end = datetime.fromisoformat(info["finished"])
    except (KeyError, TypeError, ValueError):
        return None
    return (end - start).total_seconds() / 60


def time_cost_table(loaded: dict[str, SetupResults], shared: list[str]) -> list[str]:
    keys = list(loaded)
    rows = []

    def minutes(k: str) -> str:
        values = [_minutes(i) for i in loaded[k].folder_info]
        if not values or any(v is None for v in values):
            return "—"
        return f"{sum(values):.0f} min"

    def costs(k: str) -> tuple[float, float]:
        convs = [run[n] for run in loaded[k].runs for n in shared if n in run]
        return sum(c.cost or 0.0 for c in convs), sum(c.eval_cost for c in convs)

    rows.append(("Wall-clock time (start-up included)", [minutes(k) for k in keys]))
    rows.append(("Agent cost", [money2(costs(k)[0]) for k in keys]))
    rows.append(("Simulated customer and judge cost", [money2(costs(k)[1]) for k in keys]))
    rows.append(("Total OpenAI cost", [f"**{money2(sum(costs(k)))}**" for k in keys]))
    return _table(loaded, rows)


def money2(v: float) -> str:
    return f"${v:.2f}"


def health_table(loaded: dict[str, SetupResults], shared: list[str]) -> list[str]:
    keys = list(loaded)

    def total(values: list[Optional[int]]) -> str:
        present = [v for v in values if v is not None]
        return str(sum(present)) if present else "—"

    rows = [
        (
            "Conversations ended by a timeout",
            [total([sum(r[s].timed_out for s in shared if s in r) for r in loaded[k].runs]) for k in keys],
        )
    ]
    for title, field_name in (
        ("Turns resent after a timeout", "turn_retries"),
        ("Agent LLM call timeouts", "agent_llm_timeouts"),
    ):
        rows.append(
            (title, [total([(i.get("timeouts") or {}).get(field_name) for i in loaded[k].folder_info]) for k in keys])
        )
    rows.append(
        (
            "Harness errors",
            [total([sum(r[s].harness_error for s in shared if s in r) for r in loaded[k].runs]) for k in keys],
        )
    )
    return _table(loaded, rows)


def scenario_table(loaded: dict[str, SetupResults], shared: list[str]) -> list[str]:
    keys = list(loaded)
    lines = [
        "| Scenario | " + " | ".join(f"{SETUPS[k]}, runs resolved" for k in keys) + " |",
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
        f"{len(shared)} scenarios. A run is one conversation per scenario."
    )
    out += ["", "| Setup | Result folders |", "|---|---|"]
    for k, r in loaded.items():
        out.append(f"| {SETUPS[k]} | {', '.join(f'`{f}`' for f in r.folders)} |")
    if dropped:
        out += ["", f"Left out because not every setup ran them: {', '.join(dropped)}."]
    out += ["", "## Cost per reliably resolved scenario", ""] + headline_table(loaded, shared)
    out += [
        "",
        "What one run over all scenarios costs, divided by the scenarios the setup resolved in "
        "every run. A scenario resolved only in some runs adds cost but does not count.",
    ]
    out += ["", "## Accuracy", ""] + accuracy_table(loaded, shared)
    out += ["", "## Cost", ""] + cost_table(loaded, shared)
    out += [
        "",
        "Cost is the agent's own LLM spend; the simulated customer and the judge are not "
        "included.",
        "",
        "¹ OpenAI bills cached prompt tokens at a tenth of the input price. How much it caches "
        "depends on OpenAI's side and varies between runs, so it moves the cost even when the "
        "agent uses the same tokens.",
    ]
    out += ["", "## Time and total cost", ""] + time_cost_table(loaded, shared)
    out += [
        "",
        "For all of a setup's runs together. Total OpenAI cost adds the simulated customer "
        "and the judge to the agent's own cost.",
    ]
    out += ["", "## Run health", ""] + health_table(loaded, shared)
    out += ["", "## Per scenario", ""] + scenario_table(loaded, shared)
    out += ["", "## Definitions", "", __doc__.split("Definitions:", 1)[1].strip(), ""]

    text = "\n".join(out)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "README.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"\nWrote {RESULTS_DIR / 'README.md'}")


if __name__ == "__main__":
    main()
