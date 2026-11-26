"""Counts what happened around the side question in the digression repro runs.

    python repro/digression-resume/classify.py repro/digression-resume/A [--trace]

Reads the "Tracker Events" section of every run_N.txt under the folder for the
two digression scenarios. For each run it reports:

- side turn: what the side skill did in the turn it answered the side question.
  "answer+complete" is the behaviour we want. "answer only" leaves the side
  skill active. "complete only" offers to resume before the customer hears the
  answer.
- misrouted: the customer's next message answers the paused question, but the
  paused skill's slot was not set in that turn.
- stale resume: after the paused task finished, the agent offered to resume
  the side question that was already answered.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# scenario -> (side skill, paused skill, paused slot, figures in the side answer, customer's paused answer)
SCENARIOS = {
    "rewards_digression_answers_shipping": (
        "card_advisory", "card_replace", "card_replace.shipping_type", ("180",), r"standard shipping is fine",
    ),
    "bill_digression_answers_sim_type": (
        "bill_inquiry", "sim_management", "sim_management.sim_type", ("142.50",), r"esim please",
    ),
}
TURN = re.compile(r"^\[T(\d+)\] user: (.*)$")
EVENT = re.compile(r"^\s+\d+\s+(\w+): (.*)$")
TRACKED = ("skill_activated", "skill_completed", "skill_interrupted", "skill_resumed")


def read_turns(text: str) -> list[dict]:
    """Returns the tracker events grouped by user turn."""
    section = text.split("--- Tracker Events ---", 1)[1]
    turns: list[dict] = []
    for line in section.splitlines():
        if line.startswith("---"):
            break
        if m := TURN.match(line):
            turns.append({"n": int(m.group(1)), "user": m.group(2), "events": []})
        elif (m := EVENT.match(line)) and turns:
            turns[-1]["events"].append((m.group(1), m.group(2).strip()))
    return turns


def classify(path: Path) -> dict:
    side, paused, slot, figures, reply_pattern = SCENARIOS[path.parent.name]
    turns = read_turns(path.read_text())
    start = next(
        i for i, t in enumerate(turns) if ("skill_activated", side) in t["events"]
    )
    side_turn = turns[start]["events"]
    spoke = any(k == "agent" and any(f in b for f in figures) for k, b in side_turn)
    completed = ("skill_completed", side) in side_turn
    if spoke and completed:
        side_result = "answer+complete"
    elif completed:
        side_result = "complete only"
    else:
        side_result = "answer only"

    reply = next(
        (i for i, t in enumerate(turns) if i > start and re.search(reply_pattern, t["user"], re.I)),
        None,
    )
    misrouted = reply is not None and not any(
        k == "memory_set" and b.startswith(slot) for k, b in turns[reply]["events"]
    )

    stale = False
    paused_done = False
    for t in turns[start:]:
        for k, b in t["events"]:
            if (k, b) == ("skill_completed", paused):
                paused_done = True
            if paused_done and (k, b) == ("skill_activated", "builtin_continue_interrupted"):
                stale = True
    return {
        "run": f"{path.parent.name}/{path.stem}",
        "side turn": side_result,
        "misrouted": misrouted,
        "stale resume": stale,
        "turns": turns[start : (reply or start) + 2],
        "slot": slot,
    }


def trace(result: dict) -> str:
    lines = []
    for t in result["turns"]:
        lines.append(f"    [T{t['n']}] user: {t['user'][:100]}")
        for k, b in t["events"]:
            if k == "agent":
                lines.append(f"        agent: {b[:110]}")
            elif k == "tool" and b.split("(")[0] in ("complete", "activate", "cancel"):
                lines.append(f"        tool: {b[:110]}")
            elif k in TRACKED or (k == "memory_set" and b.startswith(result["slot"])):
                lines.append(f"        {k}: {b}")
    return "\n".join(lines)


def main() -> None:
    root = Path(sys.argv[1])
    results = [
        classify(p) for p in sorted(root.rglob("run_*.txt")) if p.parent.name in SCENARIOS
    ]
    for r in results:
        print(f"{r['run']}: side turn={r['side turn']}, misrouted={r['misrouted']}, stale resume={r['stale resume']}")
        if "--trace" in sys.argv:
            print(trace(r))
    n = len(results)
    print(f"\n{n} runs")
    for label in ("answer only", "complete only", "answer+complete"):
        print(f"  side turn {label}: {sum(r['side turn'] == label for r in results)}")
    print(f"  misrouted paused answer: {sum(r['misrouted'] for r in results)}")
    print(f"  stale resume offer: {sum(r['stale resume'] for r in results)}")


if __name__ == "__main__":
    main()
