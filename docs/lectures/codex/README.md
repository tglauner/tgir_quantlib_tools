# TGIR QuantLib Tools Chronology Lecture

This folder contains an expanded 210-slide LaTeX Beamer lecture and a self-contained 20-slide summary that reconstruct the repository's development from March 2025 through August 2026. The lectures have two co-equal subjects:

1. the quantitative progression from curves and vanilla derivatives to a callable EUR/USD three-factor Monte Carlo/LSM pricer; and
2. the cohesive human-directed engineering framework that produced it.

Tim Launer guided the economics, scope, priorities, challenge questions, and acceptance decisions. Codex performed most of the foundational specification writing, Python/QuantLib programming, integration work, documentation, and test construction. Claude reviewed the Codex work and then built validation and regression extensions around it so future changes can be challenged repeatedly. The Mac Git workspace, QuantLib's C++ library and Python bindings, targeted Stack Overflow research, and the DigitalOcean runtime are treated as connected parts of that system rather than background tooling.

It is a hobby project with a deliberately serious quality standard. The hosted application costs approximately USD 7 per month on DigitalOcean. After Tim's initiating prompt, the direct workflow can proceed through specification and coding, regression testing, browser UI testing, documentation, an optional local run, DigitalOcean deployment, remote regression testing, and finally a Telegram completion notification. Telegram orchestration lives outside this repository; its credentials are not committed.

## Build

From the repository root:

```bash
make -C docs/lectures/codex
```

The outputs are `tgir_quantlib_tools_chronology.pdf` and `tgir_quantlib_tools_summary_20.pdf` in this folder. LaTeX intermediate files are isolated in the ignored `build/` subdirectory.

To build only the 20-slide summary:

```bash
make -C docs/lectures/codex summary
```

## Verify

```bash
pdfinfo docs/lectures/codex/tgir_quantlib_tools_chronology.pdf | grep '^Pages:'
pdfinfo docs/lectures/codex/tgir_quantlib_tools_summary_20.pdf | grep '^Pages:'
pdftotext docs/lectures/codex/tgir_quantlib_tools_chronology.pdf - | grep -c 'Takeaway'
```

The expanded full PDF must contain exactly 210 pages and the summary PDF exactly 20 pages. LaTeX intermediate files are ignored by the repository's global `.gitignore` rules and kept out of the source directory.

## Deliverables

- `lecture.tex` and `sections/`: full chronological lecture source.
- `tgir_quantlib_tools_chronology.pdf`: compiled 210-slide lecture.
- `summary_20.tex`: self-contained summary source.
- `tgir_quantlib_tools_summary_20.pdf`: compiled 20-slide summary.
- `collaborative_engineering_notes.md`: detailed attribution, workflow, evidence hierarchy, and extension guidance.
- `assets/`: Mac screenshots used to illustrate the governed AI-development workspace.

## Evidence basis

- Local Git history and commit diffs through `f066cce`.
- GitHub repository metadata, pull requests, CI/CD runs, and upstream QuantLib source inspected on 21 August 2026.
- Local file birth and modification timestamps, used only to refine the August 2026 sequence where the work was committed as one batch.
- Current source, JSON inputs/results, tests, architecture notes, model specifications, and deployment runbooks.
- Official QuantLib v1.43 source and release metadata.
- Official OpenAI Codex and Anthropic Claude Code guidance, plus selected Stack Overflow discussions used for discovery and then checked against current source and executable tests.

Timestamps are supporting evidence rather than a substitute for Git history: filesystem metadata can change when files are copied or synchronized. Community answers are also discovery aids rather than authority: version-pinned QuantLib source, current documentation, minimal reproductions, and regression tests govern technical conclusions. The final XCCY implementation is recorded in commit `f066cce`, which was pushed to GitHub `main` before this documentation set was committed.
