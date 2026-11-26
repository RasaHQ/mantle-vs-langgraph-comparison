# Repro: a side question pauses a task, and Mantle doesn't come back to it

A customer is partway through a task, asks a side question, gets the answer, and then answers the question the task was waiting on. Mantle often sends that answer to the side skill instead of the paused task.

## The problem

When the customer asks a side question in the middle of a task, Mantle parks the task (`INTERRUPT`) and starts the skill that can answer it. The engine offers to go back to the parked task in two cases only: when the side skill calls `complete`, or when it is cancelled (`_complete_skill` and `_route_after_cancel` in `rasa/mantle/orchestration/skill_executor.py`).

So for an open-ended side skill (one without `complete_when`), getting back depends on the model sending the answer and calling `complete` in the same response. In practice the model does one or the other:

- It sends the answer only. The turn ends with the side skill still active. The customer's next message, often the answer to the paused question, goes to the side skill.
- It calls `complete` only. The customer is asked "shall we continue where we left off?" without ever hearing the answer.

There is a third effect. When the model gets back to the task by calling `activate` on it instead of `complete`, the side skill is parked rather than finished. After the task is done, the engine offers to resume the side question, even though it was answered several turns ago.

## Setup

Two new scenarios on this branch. In both, the customer asks a side question in the middle of a task, then answers the paused question directly, without saying "let's continue".

| Scenario | Paused task | Side question, answered by | Customer's next message |
|---|---|---|---|
| [`rewards_digression_answers_shipping`](../../scenarios/cards/rewards_digression_answers_shipping.yml) | `card_replace`, at the shipping speed question | "How much have I earned in rewards on my River card?", `card_advisory` | "Okay. Standard shipping is fine." |
| [`bill_digression_answers_sim_type`](../../scenarios/sim_management/bill_digression_answers_sim_type.yml) | `sim_management`, at the eSIM or physical SIM question | "How much is my current phone bill?", `bill_inquiry` | "Okay. An eSIM please." |

`card_replace` and `sim_management` have a `complete_when` condition. `card_advisory` and `bill_inquiry` don't.

Two variants of the Mantle agent, 3 runs of each scenario per variant:

- **A** is the agent on `main`. The side skills have a `## Finishing` section telling the model when to call `complete`, including "the customer goes back to an earlier task".
- **B** is the same agent with those Finishing sections removed ([`variant-b.patch`](variant-b.patch)). This is the engine's behaviour with no help from the skill text.

Everything else is as in the main benchmark: `gpt-5.2` with no reasoning, rasa-pro `3.22.0.dev20261124122026`, simulated customer and judge on `gpt-5.1`.

## Results

[`classify.py`](classify.py) reads the tracker events of each run and counts:

| | A: with Finishing prose | B: without |
|---|---:|---:|
| Side turn: answer only, no `complete` | 5 of 6 | 6 of 6 |
| Side turn: `complete` only, answer missing | 1 of 6 | 0 of 6 |
| Side turn: answer and `complete` together | **0 of 6** | **0 of 6** |
| Customer's answer to the paused question went to the side skill | 2 of 6 | 2 of 6 |
| After the task was done, the agent offered to resume the side question | 4 of 6 | 6 of 6 |

The model never sent the answer and `complete` together. Adding prose to the skill doesn't fix it. It only changes which way the turn fails.

The judge's pass/fail (A 3 of 6, B 4 of 6) understates the problem. Two rewards runs (A run 2, B run 3) failed only because the judge read the order confirmation step as asking about shipping again. That is a wording issue in the scenario's second criterion, not agent behaviour. The counts above come from the tracker events and don't depend on the judge.

Transcripts and judge verdicts are in [`A/`](A) and [`B/`](B). Each run has a `run_N.txt` with the transcript, verdicts, and per-turn tracker events.

## What it looks like

**The answer to the paused question goes to the side skill.** From A, rewards run 1. The side skill's reply even asks the shipping question itself, but the skill stays active:

```
user:  Before that, how much have I actually earned in rewards on my River card?
agent: On your River card, you earned $180.00 cashback over the last 12 months. [...]
       When you're ready, we can continue the replacement. Do you want standard
       (5-7 business days) or rush (1-2 business days, $25) shipping?
user:  Okay. Standard shipping is fine.
agent: Got it, standard shipping.
agent: I'm sorry, I wasn't able to do that. What else can I help you with?
user:  I still need a replacement for my lost River Visa ending in 4821, with standard shipping, please.
```

In the SIM scenario the same thing happened as "I can't place the eSIM replacement order from this chat", and in variant A the customer gave up without a SIM.

**`complete` without the answer.** From A, rewards run 2:

```
user:  Before that, how much have I actually earned in rewards on my River card?
agent: Let me look up your River card rewards.
agent: I was in the middle of replacing your card. Do you want to pick up where we left off, or should I stop here?
user:  Please pick up where we left off, but first, can you tell me the exact dollar amount [...]
```

**Offer to resume a question that was already answered.** From B, bill run 1. The bill was answered at the start of this excerpt, and the SIM order has just been placed:

```
agent: Your current phone bill (June 2026) is $142.50, and it's due July 15, 2026 [...]
user:  Okay. An eSIM please.
[... eSIM order confirmed ...]
agent: We were looking into your phone bill. Would you like to pick up where we left off, or should I close that out?
```

## Suggested fix

When an open-ended skill (no `complete_when`) that was started over a parked task replies with text only, the engine should finish that skill and offer to resume the parked task in the same turn. Going back should not depend on the model calling `complete` next to its answer. Skills with a `complete_when` condition are task-shaped and should keep the current behaviour: they finish only when `complete` is called and the condition holds.

The same rule would remove the stale resume offers, because the side skill would end rather than stay parked under the task.

## Reproduce

Follow the main [README](../../README.md) for setup (`./setup.sh`, then `OPENAI_API_KEY` and `RASA_LICENSE` in `.env`). Then, from the repo root on this branch:

```bash
# Variant A: the agent as it is
./run.sh mantle --runs 3 \
  --scenario rewards_digression_answers_shipping \
  --scenario bill_digression_answers_sim_type \
  --results-dir my-repro/A
.venv-rasa/bin/python repro/digression-resume/classify.py my-repro/A --trace

# Variant B: remove the Finishing sections from the side skills
git apply repro/digression-resume/variant-b.patch
./run.sh mantle --runs 3 \
  --scenario rewards_digression_answers_shipping \
  --scenario bill_digression_answers_sim_type \
  --results-dir my-repro/B
.venv-rasa/bin/python repro/digression-resume/classify.py my-repro/B --trace
git checkout -- agents/   # back to variant A
```

Each variant takes about 2 minutes and costs about $1 to $2 in OpenAI usage. `--trace` prints the side-question turns with the agent's messages, `activate` and `complete` calls, and skill stack events.
