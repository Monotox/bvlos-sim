# Project Knowledge Graph

bvlos-sim keeps a persistent Graphify knowledge graph in `graphify-out/`. It
indexes code, schemas, tests, examples, and documentation so architecture work
can begin from scoped relationships instead of broad text searches. The graph
was the starting point for the simulation-safety and accuracy audit: it exposed
cross-file model paths, public-contract consumers, and areas requiring focused
math, science, and operational-readiness review.

Graphify is a navigation and review aid. Source code, cited standards, tests,
and measured flight evidence remain authoritative; a graph result is not proof
that a model or operation is correct.

## Project-local setup

The repository owns its Graphify workflow:

- `AGENTS.md` defines the graph-first codebase rules.
- The repository-local hook invokes `graphify hook-check` from the
  contributor's `PATH`.
- `graphify-out/` contains the persistent project graph and reports.

No Graphify configuration in a contributor's home directory is required. The
CLI itself must be available on `PATH`. With uv installed:

```bash
uv tool install --upgrade graphifyy
graphify --version
```

## Query before browsing

When `graphify-out/graph.json` exists, start codebase and architecture questions
with the smallest applicable query:

```bash
graphify query "Where is RTH reserve computed and exposed?"
graphify path "MissionPlan" "RthReservePoint"
graphify explain "operational readiness"
```

- `query` returns a scoped subgraph for a natural-language question.
- `path` shows the relationship between two known concepts or symbols.
- `explain` focuses on one concept and its immediate context.

Use `graphify-out/wiki/index.md` for broad navigation when that optional output
exists. Read `graphify-out/GRAPH_REPORT.md` for whole-project architecture
reviews, or when a scoped query does not provide enough context. Follow a graph
result into the cited source and tests before changing behavior.

Dirty files under `graphify-out/` are normal after hooks, queries, and updates;
they are not a reason to skip the graph-first workflow.

## Keep the graph current

After changing code, schemas, examples, or documentation, update and validate
the graph from the repository root:

```bash
graphify update .
graphify diagnose multigraph --graph graphify-out/graph.json
```

For a substantial investigation, save only reusable conclusions and then fold
them into the graph's lessons:

```bash
graphify save-result \
  --question "What safety gaps were closed?" \
  --answer "Concise, source-backed summary" \
  --type query \
  --outcome useful
graphify reflect --graph graphify-out/graph.json
```

Review saved memory before committing it: do not persist secrets, credentials,
personal data, private incident details, or unsupported conclusions.

## Version-control policy

Commit the current root graph, manifest, portable architecture report, and
genuinely reusable memory/reflections when they changed with the project. Do
not commit Graphify's local interpreter metadata, health report with
machine-specific installation paths, extraction cache, or date-stamped
snapshots; `graphify-out/.gitignore` excludes those generated working files.

A normal handoff therefore includes:

1. Relevant `query`, `path`, or `explain` output checked against source.
2. Code, tests, contracts, and documentation updated together.
3. The full project checks run independently of Graphify.
4. `graphify update .` and graph diagnostics run after the final edit.

This keeps the graph useful to the next human contributor without treating it
as a substitute for engineering evidence.
