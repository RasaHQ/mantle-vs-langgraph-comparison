"""Run the Mantle vs LangGraph benchmark.

    python harness/run.py mantle lg lg-high --batches 3

Each batch runs every scenario in ``scenarios/`` 3 times against one setup and
writes the per-run results to ``results/<setup>/<timestamp>/``. At the end,
``harness/compare.py`` rebuilds the comparison table in ``results/README.md``.

Quick check that everything starts (one short conversation per setup, results
kept out of ``results/``):

    python harness/run.py mantle lg lg-high --batches 1 --runs 1 \
        --scenario order_status_happy_path --results-dir logs/smoke

The simulated user, the LLM judge and the assertions all come from rasa-pro's
evaluation harness (``rasa.builder.copilot.mcp_server.tools``). This script only
starts the servers, hands the scenarios to ``run_scenarios`` and copies the
results out.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]
SCENARIOS_DIR = REPO / "scenarios"
CONFTEST = REPO / "harness" / "conftest.yml"
LOGS_DIR = REPO / "logs"
LANGGRAPH_PYTHON = REPO / ".venv-langgraph" / "bin" / "python"

MCP_PORT = 8001
MANTLE_PORT = 5005
LANGGRAPH_PORT = 5007


@dataclass(frozen=True)
class Setup:
    name: str
    engine: str  # agent directory under agents/
    reasoning_effort: Optional[str]  # LangGraph only
    langgraph_llm_timeout_s: Optional[float]  # LangGraph only, per LLM call
    turn_timeout_s: float  # harness wait for the agent's reply to one user turn
    run_timeout_s: float  # harness limit for one whole conversation
    parallelism: int  # conversations in flight at once


SETUPS = {
    "mantle": Setup("mantle", "mantle_combined", None, None, 30, 600, 4),
    "lg": Setup("lg", "langgraph_native", "none", 30, 30, 600, 15),
    # Reasoning makes turns slow. Limits are raised so no run fails on a timeout.
    "lg-high": Setup("lg-high", "langgraph_native", "high", 300, 300, 3600, 15),
}

# Concurrent LLM calls for the simulated user and for the judge.
SIM_LLM_CAP = 4
EVAL_LLM_CAP = 4


def log(message: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


# --- environment ----------------------------------------------------------


def load_env_file(path: Path) -> None:
    """Load KEY=VALUE lines into os.environ without overriding set variables."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def prepare_environment() -> None:
    load_env_file(REPO / ".env")
    missing = [k for k in ("OPENAI_API_KEY", "RASA_LICENSE") if not os.environ.get(k)]
    if missing:
        sys.exit(f"Missing {', '.join(missing)}. Set them in .env (see .env.example).")
    os.environ.setdefault("MCP_BANKING_TOKEN", "test-token")
    os.environ["MCP_SERVER_URL"] = f"http://localhost:{MCP_PORT}/mcp/"
    # Report each conversation's agent LLM cost (engine_tokens) from the Rasa server.
    os.environ["RASA_COLLECT_ENGINE_TOKEN_USAGE"] = "1"
    os.environ["SANIC_WORKERS"] = "1"
    # Turn on the harness's tool-call scoring, repair and extra metrics.
    os.environ["RASA_FEATURE_FLAG_SIM_EVAL_EXTENDED"] = "true"


# --- processes --------------------------------------------------------------


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def start(cmd: list[str], cwd: Path, log_path: Path, env: Optional[dict] = None) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(log_path, "w", encoding="utf-8")
    return subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env or os.environ.copy(),
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait(timeout=10)
    except ProcessLookupError:
        pass


def wait_until(check, proc: subprocess.Popen, timeout_s: float, what: str, log_path: Path) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"{what} exited early; see {log_path}")
        if check():
            return
        time.sleep(0.5)
    raise RuntimeError(f"{what} not ready after {timeout_s:.0f}s; see {log_path}")


def http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.status == 200
    except OSError:
        return False


def start_mcp(log_dir: Path) -> subprocess.Popen:
    log_path = log_dir / "mcp_server.log"
    proc = start([sys.executable, "-m", "shared_mcp_server.server"], REPO, log_path)
    wait_until(lambda: port_in_use(MCP_PORT), proc, 30, "MCP server", log_path)
    return proc


def start_mantle(project: Path, log_dir: Path) -> subprocess.Popen:
    rasa = str(Path(sys.executable).parent / "rasa")
    for cache in (REPO / ".rasa", project / ".rasa"):
        shutil.rmtree(cache, ignore_errors=True)
    log("training mantle_combined ...")
    with open(log_dir / "train.log", "w", encoding="utf-8") as handle:
        subprocess.run(
            [rasa, "train", "--debug"], cwd=project, check=True, stdout=handle, stderr=subprocess.STDOUT
        )
    log_path = log_dir / "server.log"
    proc = start(
        [rasa, "run", "--debug", "--enable-api", "--inspect", "--cors", "*", "-p", str(MANTLE_PORT)],
        project,
        log_path,
    )
    wait_until(lambda: http_ok(f"http://localhost:{MANTLE_PORT}/status"), proc, 180, "Mantle server", log_path)
    return proc


def start_langgraph(setup: Setup, project: Path, log_dir: Path) -> subprocess.Popen:
    if not LANGGRAPH_PYTHON.exists():
        sys.exit(f"{LANGGRAPH_PYTHON} not found. Run ./setup.sh first.")
    env = os.environ.copy()
    env["LANGGRAPH_REASONING_EFFORT"] = setup.reasoning_effort or "none"
    env["LANGGRAPH_LLM_TIMEOUT_S"] = str(setup.langgraph_llm_timeout_s)
    log_path = log_dir / "server.log"
    proc = start(
        [str(LANGGRAPH_PYTHON), "-m", "langgraph_native.server", "--host", "127.0.0.1", "--port", str(LANGGRAPH_PORT)],
        project,
        log_path,
        env,
    )
    wait_until(lambda: http_ok(f"http://127.0.0.1:{LANGGRAPH_PORT}/status"), proc, 180, "LangGraph server", log_path)
    if "Knowledge index unavailable" in log_path.read_text(encoding="utf-8"):
        raise RuntimeError(f"LangGraph knowledge index failed to build; see {log_path}")
    return proc


# --- evaluation -------------------------------------------------------------


def route_harness_logs(path: Path) -> None:
    """Send rasa-pro's harness logs (debug level, full prompts) to a file, not the console."""
    import structlog

    structlog.configure(
        logger_factory=structlog.PrintLoggerFactory(file=open(path, "a", encoding="utf-8")),
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
    )


def scenario_paths(only: Optional[list[str]] = None) -> list[Path]:
    paths = sorted(SCENARIOS_DIR.rglob("*.yml"))
    if only:
        paths = [p for p in paths if p.stem in only]
        missing = set(only) - {p.stem for p in paths}
        if missing:
            sys.exit(f"Unknown scenario(s): {', '.join(sorted(missing))}")
    return paths


def stage(project: Path, only: Optional[list[str]]) -> None:
    """Put the conftest and scenarios where the rasa-pro harness looks for them."""
    eval_dir = project / "eval"
    shutil.rmtree(eval_dir, ignore_errors=True)
    (eval_dir / "scenarios").mkdir(parents=True)
    shutil.copy2(CONFTEST, eval_dir / "conftest.yml")
    for path in scenario_paths(only):
        shutil.copy2(path, eval_dir / "scenarios" / path.name)


async def evaluate(setup: Setup, project: Path, server_url: str, timestamp: str, runs: int) -> None:
    from rasa.builder.copilot.mcp_server.tools import text_simulation
    from rasa.builder.copilot.mcp_server.tools.artifact_writer import write_experiment_summary
    from rasa.builder.copilot.mcp_server.tools.eval_config import build_llm_client, load_conftest
    from rasa.builder.copilot.mcp_server.tools.evaluate_agent import run_scenarios
    from rasa.builder.copilot.mcp_server.tools.scenario import load_scenario

    # The harness waits 30s for a reply to one user turn. Set it per setup.
    text_simulation._send_message.__kwdefaults__["timeout"] = setup.turn_timeout_s
    os.environ["EVAL_AGENT"] = setup.engine

    conftest = load_conftest(project)
    scenarios = [load_scenario(p) for p in sorted((project / "eval" / "scenarios").glob("*.yml"))]
    total = len(scenarios) * runs
    done = 0

    def on_run_finished() -> None:
        nonlocal done
        done += 1
        if done % 5 == 0 or done == total:
            log(f"{setup.name}: {done}/{total} conversations")

    entries, wall_clock_s = await run_scenarios(
        scenarios=scenarios,
        project_path=project,
        experiment_timestamp=timestamp,
        run_count=runs,
        parallelism=setup.parallelism,
        rasa_server_url=server_url,
        simulation_llm_client=build_llm_client(conftest.simulation.llm),
        eval_llm_client=build_llm_client(conftest.evaluation.llm),
        eval_llm_config=conftest.evaluation.llm,
        show_tracker_events=True,
        evaluate_tool_calls=True,
        simulation_max_concurrent_llm_calls=SIM_LLM_CAP,
        eval_max_concurrent_llm_calls=EVAL_LLM_CAP,
        per_run_timeout_s=setup.run_timeout_s,
        on_run_finished=on_run_finished,
    )
    if entries:
        write_experiment_summary(project, timestamp, entries, wall_clock_s=wall_clock_s)


def package_version(name: str, python: Optional[Path] = None) -> Optional[str]:
    if python is None:
        try:
            return metadata.version(name)
        except metadata.PackageNotFoundError:
            return None
    out = subprocess.run(
        [str(python), "-c", f"from importlib.metadata import version; print(version({name!r}))"],
        capture_output=True,
        text=True,
    )
    return out.stdout.strip() or None


def git_commit() -> Optional[str]:
    out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True)
    return out.stdout.strip() or None


def run_batch(setup: Setup, runs: int, only: Optional[list[str]], results_dir: Path) -> Path:
    for port in (MCP_PORT, MANTLE_PORT, LANGGRAPH_PORT):
        if port_in_use(port):
            sys.exit(f"Port {port} is in use. Stop that process first.")

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    project = REPO / "agents" / setup.engine
    out_dir = results_dir / setup.name / timestamp
    log_dir = LOGS_DIR / f"{setup.name}_{timestamp}"
    log_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now().isoformat(timespec="seconds")
    log(f"{setup.name}: batch {timestamp}, {len(scenario_paths(only))} scenarios x {runs} runs")

    procs: list[subprocess.Popen] = []
    try:
        procs.append(start_mcp(log_dir))
        if setup.engine == "mantle_combined":
            procs.append(start_mantle(project, log_dir))
            server_url = f"http://localhost:{MANTLE_PORT}"
        else:
            procs.append(start_langgraph(setup, project, log_dir))
            server_url = f"http://127.0.0.1:{LANGGRAPH_PORT}"
        stage(project, only)
        route_harness_logs(log_dir / "harness.log")
        asyncio.run(evaluate(setup, project, server_url, timestamp, runs))
        shutil.copytree(project / "eval" / "results" / timestamp, out_dir)
    finally:
        for proc in reversed(procs):
            stop(proc)
        shutil.rmtree(project / "eval", ignore_errors=True)

    info = {
        "setup": asdict(setup),
        "runs_per_scenario": runs,
        "started": started,
        "finished": datetime.now().isoformat(timespec="seconds"),
        "repo_commit": git_commit(),
        "rasa_pro": package_version("rasa-pro"),
        "langgraph": package_version("langgraph", LANGGRAPH_PYTHON) if setup.engine != "mantle_combined" else None,
        "langchain_core": package_version("langchain-core", LANGGRAPH_PYTHON) if setup.engine != "mantle_combined" else None,
        "python": platform.python_version(),
        "sim_llm_cap": SIM_LLM_CAP,
        "eval_llm_cap": EVAL_LLM_CAP,
    }
    (out_dir / "run_info.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    log(f"{setup.name}: results in {out_dir}")
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("setups", nargs="+", choices=sorted(SETUPS), help="setups to run, in order")
    parser.add_argument("--batches", type=int, default=3, help="batches per setup (default 3)")
    parser.add_argument("--runs", type=int, default=3, help="runs per scenario in each batch (default 3)")
    parser.add_argument("--scenario", action="append", help="run only this scenario (repeatable)")
    parser.add_argument("--results-dir", type=Path, default=REPO / "results", help="default: results/")
    args = parser.parse_args()
    results_dir = args.results_dir.resolve()
    prepare_environment()
    for name in args.setups:
        for batch in range(1, args.batches + 1):
            log(f"=== {name}: batch {batch}/{args.batches}")
            run_batch(SETUPS[name], args.runs, args.scenario, results_dir)
    subprocess.run([sys.executable, str(REPO / "harness" / "compare.py"), str(results_dir)], check=True)


if __name__ == "__main__":
    main()
