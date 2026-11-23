# Mantle vs LangGraph

This repo compares two customer-service agents that do the same job: a **Mantle** agent built with Rasa Pro, and a **LangGraph** agent written by hand. Both are scored on the same 31 multi-turn conversations. Each conversation is driven by an LLM playing the customer and graded by an LLM judge plus rule-based assertions.

The latest numbers are in [`results/README.md`](results/README.md).

## What is compared

Both agents serve the same fictional bank and telecom company ("Acme Bank & Telecom"). They cover card replacement, card and account advice, order status, lost or stolen SIMs, and bill questions. Both call the same mock backend tools, served by one MCP server (`shared_mcp_server/`), and use the same model, `gpt-5.2`.

| Setup | Agent | Notes |
|---|---|---|
| `mantle` | [`agents/mantle_combined`](agents/mantle_combined) | Rasa Pro 3.22.0.dev5. Skills in `skills/*/skill.md`, agent rules in `agent.yml`. |
| `lg` | [`agents/langgraph_native`](agents/langgraph_native) | LangGraph supervisor with one specialist per task. A router picks the specialist on every message, and every model call sees the same skill descriptions Mantle uses (`routing` in `data/agent.yml`). No reasoning (`reasoning_effort="none"`), like Mantle. |
| `lg-high` | same as `lg` | `reasoning_effort="high"`. Timeouts are raised so no run fails on a timeout (below). |

The scenarios are in [`scenarios/`](scenarios): billing (1), cards (11), order status (7) and SIM management (12). Each scenario has:
- instructions for the simulated customer,
- the criteria the judge checks,
- assertions on the conversation, such as which tools were called and what the agent said.

Both agents run the identical files.

## Requirements

- macOS or Linux, and [uv](https://docs.astral.sh/uv/getting-started/installation/). `uv` installs Python 3.11 when needed.
- An OpenAI API key.
- A Rasa Pro license (`RASA_LICENSE`) for the Mantle agent. The free Developer Edition license works: [request one here](https://rasa.com/rasa-pro-developer-edition-license-key-request).
- Ports 5005, 5007 and 8001 free.

## Run it

```bash
./setup.sh          # creates .venv-rasa and .venv-langgraph from requirements/*.lock.txt, and .env
# put OPENAI_API_KEY and RASA_LICENSE in .env
./run.sh --smoke    # optional: one short conversation per setup, results in logs/smoke
./run.sh            # full benchmark, then writes results/README.md
```

`./run.sh` runs each setup in 3 sets. Each set runs all 31 scenarios 3 times, so every scenario gets 9 conversations per setup. Sets are interleaved (set 1 of every setup, then set 2, then set 3), so changes in the OpenAI API over the run affect all setups alike. The table is rebuilt from everything in `results/` at the end, and `python harness/compare.py` rebuilds it on its own. Other forms:

```bash
./run.sh lg-high                 # one setup
./run.sh mantle lg --sets 1      # fewer sets
.venv-rasa/bin/python harness/run.py --help
```

A full run took just under 2 hours and cost about $150 in OpenAI usage. Per set, counting the agent, the simulated customer and the judge:

| Setup | Time per set | Cost per set |
|---|---:|---:|
| `mantle` | ~10 min | ~$15 |
| `lg` | ~7 min | ~$12 |
| `lg-high` | ~20 min | ~$22 |

On macOS, `run.sh` keeps the machine awake with `caffeinate` while it runs. Sleep freezes the timeouts and drops the open connections to OpenAI, which would ruin the conversations in flight. Closing the lid still sleeps the machine, so keep it open.

## How a set runs

`harness/run.py` does the following for one set:

1. Starts the MCP tool server.
2. Starts the agent. For Mantle that means `rasa train` and `rasa run`. For LangGraph it starts `langgraph_native.server` in its own environment.
3. Calls rasa-pro's evaluation harness (`rasa.builder.copilot.mcp_server.tools.evaluate_agent.run_scenarios`) with the scenarios and `harness/conftest.yml`. The simulated customer and the judge are `gpt-5.1` with no reasoning and no caching.
4. Copies the results to `results/<setup>/<timestamp>/`.

Server logs go to `logs/`, which is not committed.

| Setting | `mantle` | `lg` | `lg-high` |
|---|---:|---:|---:|
| Agent model call timeout | 30s | 30s | 300s |
| Wait for one agent reply | 30s | 30s | 300s |
| Limit for one conversation | 600s | 600s | 3600s |
| Conversations in parallel | 10 | 15 | 15 |

All settings are in `SETUPS` at the top of `harness/run.py`.

## Scoring

A **run** is one pass over the suite: one conversation for each of the 31 scenarios. A full benchmark gives each setup 9 runs (3 sets of 3).

- A **conversation passes** when the judge passes every criterion and every assertion holds.
- **Scenarios passed per run** counts the passing conversations in one run.
- **Cost** is the agent's own LLM spend per conversation (`engine_tokens.cost` in each conversation's JSON). It excludes the simulated customer and the judge.
- The **cost head-to-head** divides Mantle's cost per conversation by the other setup's in each run, on the same scenarios: all of them, or only those both passed in that run. Per-setup "passing only" costs cover different scenarios for each agent, so don't compare them across columns.

Every metric is computed per run, and the table shows the mean ± the sample standard deviation across the 9 runs. For example, `26.1/31 ± 1.5` means a run passes 26.1 scenarios on average, and a typical run lands within about 1.5 of that. Single runs vary a lot. With 3 runs per scenario, the `lg-high` setup has passed anywhere from 21 to 26 of 31 scenarios on the same code. That is why each setup gets 9 runs.

## Layout

```
agents/mantle_combined/    Mantle agent (Rasa Pro project)
agents/langgraph_native/   LangGraph agent
shared_mcp_server/         MCP server with the mock tools both agents call
shared_mock_data/          Mock customers, cards, orders and bills behind those tools
scenarios/                 The 31 test conversations
harness/run.py             Starts servers, runs sets, copies results
harness/compare.py         Builds results/README.md from results/
harness/conftest.yml       Simulated customer and judge model settings
requirements/              Pinned packages for each environment
results/                   Per-run JSON and transcripts, and the comparison table
```

Each run in `results/<setup>/<timestamp>/<scenario>/` has a `run_N.txt` with the transcript and the judge's verdicts, and a `run_N.json` with:
- tokens and cost for the agent, the simulated customer and the judge,
- per-turn latency,
- assertion results.

`run_info.json` records the settings and package versions for that set.
