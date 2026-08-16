# Embedding Similarity — Clarification Questions

## Ambiguity 1: Runtime name still unclear
://omlx.ai/hp_FlXP1hu9eseftDoIBhyqYp2jyPurU12i8DMA
Question 1 asked to confirm the runtime for `google/embeddinggemma-300m`. You originally wrote "olmx" in
chat, then answered "E) Other: omlx" in the questions file — two different spellings, neither matching a
runtime I can identify with confidence. This affects real design decisions: whether the Ingestion Worker
calls out to a separate local server process over HTTP (like it already does for OpenRouter), or loads the
model in-process via a Python/native library with no separate service to run, deploy, or health-check.

### Clarification Question 1
Which of these is closest to what you meant?

A) **Ollama** — a local server process (`ollama serve`) exposing an HTTP API; the Worker would call it over
the network, similar in shape to the existing OpenRouter integration

B) **MLX** (Apple's `mlx-lm` / `mlx-embeddings`) — an in-process Python library, no separate server; ties
the Ingestion Worker to running on Apple Silicon specifically

C) A different specific tool/library you have in mind (not listed above) — please name it exactly

D) Not sure yet / open to a recommendation — happy to have this decided during NFR Requirements based on
what best fits a Docker-based Linux deployment (this project's existing target, per its NFR history)

[Answer]: https://omlx.ai — confirmed via web search: **oMLX** is a real, legitimate local inference server
built on Apple's MLX framework (menu-bar app on macOS, OpenAI-compatible API at `localhost:8000`, supports
embedding models). Not option A (Ollama) or B (bare MLX library) as originally offered — it's a specific
third product, now identified precisely.

## Ambiguity 2: oMLX is macOS/Apple-Silicon-native — it cannot run inside this project's existing Docker containers
Every other piece of this stack (API Service, Database, Frontend, Ingestion Worker) is fully containerized
and reproducible with a single `docker-compose up`. oMLX runs natively on the Mac host, not inside a Linux
container (Apple Silicon acceleration isn't available inside Docker Desktop's Linux VM) — so the Ingestion
Worker container would need to call out to a service running on the host (e.g. `host.docker.internal:8000`)
rather than a peer container. This is a real deployment-topology difference worth deciding deliberately.

### Clarification Question 2
How should this operational dependency be handled?

A) **Accept it** — oMLX runs natively on the Mac host, started separately (its own menu-bar app, outside
`docker-compose`); the Ingestion Worker container reaches it via `host.docker.internal`; this becomes a
new, documented manual prerequisite for running the project locally (would need to be revisited if this
project is ever deployed to a non-Mac host)

B) **Use a containerizable alternative instead** — e.g. Ollama, which ships official Linux Docker images and
can run as a normal `docker-compose` service on any host, keeping the whole stack single-command-reproducible
(would not be oMLX specifically, but would still serve the same `embeddinggemma-300m` model)

C) Other (please describe after [Answer]: tag below)

[Answer]:i will insyall and serve up the endpoint. yyou just need to provide vonfig to point to it.

