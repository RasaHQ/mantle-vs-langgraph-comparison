#!/usr/bin/env bash
# Creates the two Python environments the benchmark needs.
#   .venv-rasa       rasa-pro 3.22.0.dev20261124122026: Mantle agent, mock tool server, evaluation harness
#   .venv-langgraph  LangGraph agent
# They are separate because rasa-pro and the LangGraph agent pin different
# versions of litellm and websockets.
set -euo pipefail
cd "$(dirname "$0")"

command -v uv >/dev/null || { echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/" >&2; exit 1; }

uv venv --allow-existing -p 3.11 .venv-rasa
uv pip install -p .venv-rasa/bin/python -r requirements/rasa.lock.txt

uv venv --allow-existing -p 3.11 .venv-langgraph
uv pip install -p .venv-langgraph/bin/python -r requirements/langgraph.lock.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env. Add your OPENAI_API_KEY and RASA_LICENSE to it."
fi
echo "Setup done. Next: ./run.sh"
