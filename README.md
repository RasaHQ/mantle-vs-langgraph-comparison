# Mantle vs LangGraph

This repo compares two customer-service agents that do the same job: a **Mantle** agent built with Rasa Pro, and a **LangGraph** agent written by hand. Both are scored on the same 31 multi-turn conversations. Each conversation is driven by an LLM playing the customer and graded by an LLM judge plus rule-based assertions.

## Results

Every scenario runs 3 times per setup. A scenario counts as **solved reliably** when it passes in all 3 runs.

| Setup | Scenarios solved reliably | Cost per reliably solved scenario |
|---|---:|---:|
| **Mantle** | **27/31** (87%) | **$0.129** |
| LangGraph | 19/31 (61%) | $0.149 |
| LangGraph, reasoning high | 21/31 (68%) | $0.323 |

> **Main takeaway:** Mantle solves more scenarios, and solves them more consistently from run to run. LangGraph costs less per conversation, but fails more of them, so per scenario it solves reliably it costs more. Turning on high reasoning helps LangGraph a little and more than doubles its cost.

**Accuracy**

| | Mantle | LangGraph | LangGraph, reasoning high |
|---|---:|---:|---:|
| pass^1: scenarios passed in at least 1 of 3 runs | **31/31** | 28/31 | 28/31 |
| pass^2: scenarios passed in at least 2 of 3 runs | **30/31** | 25/31 | 26/31 |
| pass^3: scenarios passed in all 3 runs | **27/31** | 19/31 | 21/31 |

**Cost** (the agent's own LLM spend, `gpt-5.2`)

| | Mantle | LangGraph | LangGraph, reasoning high |
|---|---:|---:|---:|
| **Cost per reliably solved scenario** | **$0.129** | $0.149 | $0.323 |
| Cost per resolved conversation | $0.119 | $0.118 | $0.271 |
| Cost per conversation | $0.112 | $0.091 | $0.219 |

**How the cost rows are computed**

Each setup ran 31 scenarios 3 times: 93 conversations. Total cost is the agent's LLM spend summed over all 93 conversations, resolved or not.

| | Mantle | LangGraph | LangGraph, reasoning high |
|---|---:|---:|---:|
| Total cost, 93 conversations | $10.46 | $8.50 | $20.34 |
| Conversations resolved | 88 | 72 | 75 |
| Scenarios solved reliably (passed in all 3 runs) | 27 | 19 | 21 |

- **Cost per conversation** = total cost ÷ 93 conversations. Mantle: $10.46 ÷ 93 = $0.112.
- **Cost per resolved conversation** = total cost ÷ conversations resolved. Mantle: $10.46 ÷ 88 = $0.119.
- **Cost per reliably solved scenario** = (total cost ÷ 3 runs) ÷ scenarios solved reliably. Total cost ÷ 3 is what one run over all 31 scenarios costs. Mantle: $10.46 ÷ 3 ÷ 27 = $0.129.

The full tables, the per-scenario breakdown, and the definitions are in [`results/README.md`](results/README.md). Every conversation's transcript and judge verdicts are in [`results/`](results).

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

`./run.sh` runs one set per setup: all 31 scenarios 3 times, so every scenario gets 3 conversations per setup. All setups run 15 conversations at a time. With `--sets N`, sets are interleaved (set 1 of every setup, then set 2, and so on), so changes in the OpenAI API over the run affect all setups alike. The table is rebuilt from everything in `results/` at the end, and `python harness/compare.py` rebuilds it on its own. Other forms:

```bash
./run.sh lg-high                 # one setup
./run.sh --sets 3                # 9 runs per scenario
.venv-rasa/bin/python harness/run.py --help
```

A full run takes about 35 minutes and costs about $50 in OpenAI usage. Per set, counting the agent, the simulated customer and the judge:

| Setup | Time per set | Cost per set |
|---|---:|---:|
| `mantle` | ~8 min | ~$15 |
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
| Conversations in parallel | 15 | 15 | 15 |

All settings are in `SETUPS` at the top of `harness/run.py`.

## Scoring

A **run** is one pass over the suite: one conversation for each of the 31 scenarios. A default benchmark gives each setup 3 runs.

- A conversation is **resolved** when the judge passes every criterion and every assertion holds.
- **pass^k** counts the scenarios resolved in at least k of their runs. pass^1 shows what a setup can do; pass^3 shows what it does every time.
- A scenario is **solved reliably** when it is resolved in every run.
- **Cost** is the agent's own LLM spend per conversation (`engine_tokens.cost` in each conversation's JSON). It excludes the simulated customer and the judge.
- **Cost per reliably solved scenario**, the headline, is what one run over all scenarios costs, divided by the scenarios solved reliably. A scenario that passes only sometimes adds cost but does not count as solved.
- **Cost per resolved conversation** is the total cost of all conversations, resolved or not, divided by the conversations resolved.

Single runs vary: the same agent can pass a scenario in one run and fail it in the next, which is why the headline counts only scenarios solved every time. Use `--sets 3` for 9 runs per scenario.

Cost also depends on OpenAI's prompt caching, which varies with time of day and load. In our testing the share of Mantle's prompt served from cache ranged from 13% to 38% on identical code, which moved its cost per conversation by up to about 25%. `results/README.md` reports the cache share next to the cost.

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
