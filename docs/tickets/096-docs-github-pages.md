# Ticket 096: Documentation Site on GitHub Pages

## Status

Implemented.

## Close-out notes

- `mkdocs.yml` (repo root) uses MkDocs Material with an explicit `nav`,
  `strict: true`, and `not_in_nav: /tickets/[0-9]*.md` so the numbered ticket
  files stay reachable from the **Ticket Backlog** page without each becoming a
  top-level nav entry (and without tripping the strict "not in nav" check).
- `docs/index.md` is the landing page; every existing `docs/*.md` and the ticket
  backlog render under `nav`. `mkdocs build --strict` passes with no warnings.
- Toolchain is isolated in the `docs` dependency group
  (`uv sync --only-group docs`); core `uv sync` / CI does not pull it in.
- `.github/workflows/docs.yml` runs `mkdocs build --strict` on PRs touching
  `docs/**` or `mkdocs.yml`, and builds + deploys to GitHub Pages on push to
  `main` via `upload-pages-artifact` + `deploy-pages`.
- **One-time manual step (cannot be done from code):** in the repository
  settings, set **Settings → Pages → Build and deployment → Source** to
  **GitHub Actions**. Until this is done the deploy job will fail; the PR
  build-check works regardless. The published URL is
  `https://monotox.github.io/bvlos-sim/`.

## Goal

Publish the existing `docs/` markdown as a browsable documentation website on
GitHub Pages, built and deployed automatically from `main`. Today the docs
(USAGE, the project brief, roadmap, code style, versioning policy, SITL guides,
field semantics, and the ticket backlog) are only readable as raw markdown in
the repository. A rendered site with navigation and search makes the project
far more approachable for operators and open-source contributors.

## Why This Is High Impact

`docs/USAGE.md` alone is ~58 KB. A first-time visitor evaluating the tool has to
scroll a single giant markdown file on GitHub. A proper docs site with a sidebar,
section navigation, search, and deep links is the difference between "looks
abandoned" and "looks maintained" in the first 30 seconds — the window in which
most contributors decide whether to engage.

This is also a low-risk, self-contained change: it adds tooling and CI, touches
no estimator or schema code, and cannot affect determinism or existing tests.

## Scope

### Static site generator

Use **MkDocs with the Material theme** (the de-facto standard for Python project
docs: markdown-native, built-in search, good navigation, minimal config). The
existing `docs/` directory becomes the MkDocs `docs_dir`, so the markdown files
are published in place — they are *not* physically moved.

### Configuration

Add a repo-root `mkdocs.yml`:

- `site_name`, `repo_url`, and `site_description`.
- `theme: material` with navigation, search, and a dark/light toggle.
- An explicit `nav:` tree grouping the existing docs, for example:
  - Home (`docs/index.md` — a short landing page; may summarise the brief)
  - Usage (`USAGE.md`)
  - Project Brief (`BVLOS_MISSION_SIMULATOR_BRIEF.md`)
  - Roadmap (`ROADMAP.md`)
  - Field Semantics (`ESTIMATOR_V1_FIELD_SEMANTICS.md`)
  - Versioning Policy (`VERSIONING_POLICY.md`)
  - SITL (`SITL_ADAPTER_CONTRACT.md`, `SITL_LOCAL_SETUP.md`)
  - Contributing (`CODE_STYLE.md`)
  - Backlog (`tickets/README.md`)
- `strict: true` so broken internal links and nav references fail the build.

### Landing page

Add `docs/index.md` as the site home (MkDocs needs an index). It should be a
concise overview with links into Usage and the Brief. It may reuse content from
the repository `README.md`, but keep the canonical source single — do not
duplicate large blocks; link instead.

### Dependencies

Add a `docs` optional dependency group (e.g. `mkdocs-material`) so the site
toolchain is isolated from the runtime/test dependencies and is not pulled into
core CI.

### CI / deployment

Add `.github/workflows/docs.yml`:

- On pull requests touching `docs/**` or `mkdocs.yml`: run `mkdocs build --strict`
  to catch broken links and nav errors (build-only, no deploy).
- On push to `main`: build and deploy to GitHub Pages using the official
  `actions/configure-pages` + `actions/upload-pages-artifact` +
  `actions/deploy-pages` flow (or `mkdocs gh-deploy`), with the minimal
  `pages: write` / `id-token: write` permissions.

The existing `ci.yml` is left unchanged; docs build is a separate workflow so a
docs-only change never blocks on the test matrix and vice versa.

### Repository settings (manual, documented)

GitHub Pages must be enabled with the "GitHub Actions" source. Document this
one-time manual step in the ticket close-out / CONTRIBUTING note, since it
cannot be done from code.

### Files to create or modify

| File | Change |
|---|---|
| `mkdocs.yml` | New — MkDocs Material config with explicit `nav` and `strict: true` |
| `docs/index.md` | New — site landing page |
| `.github/workflows/docs.yml` | New — PR build-check + deploy-on-main to GitHub Pages |
| `pyproject.toml` | Add a `docs` optional-dependency group (`mkdocs-material`) |
| `README.md` | Add a link to the published docs site |
| `docs/USAGE.md` (and siblings) | Fix any internal links that `--strict` flags |

## Non-goals

- No API/docstring autogeneration (`mkdocstrings`) in this ticket — it can be a
  follow-up once the static site exists.
- No custom domain; the default `*.github.io` URL is sufficient.
- No restructuring or rewriting of existing docs content beyond fixing links the
  strict build rejects.

## Acceptance criteria

1. `mkdocs build --strict` succeeds locally with no warnings, rendering every
   file listed in `nav`.
2. A pull request that changes a `docs/` file runs the docs build check in CI.
3. Merging to `main` publishes the site to GitHub Pages automatically.
4. Every current `docs/*.md` (and the ticket backlog) is reachable from the site
   navigation.
5. No change to estimator behaviour, schemas, or the existing test suite; core
   CI is unaffected.
