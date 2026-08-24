# Human-Directed Two-Agent Quantitative Engineering

## The central project result

This project produced two co-equal achievements. The first is a complex callable EUR/USD cross-currency pricer using two Hull–White rate factors, lognormal FX, calibration, exact-transition Monte Carlo, and two-pass Longstaff–Schwartz exercise. The second is the cohesive development system that made that result possible.

Tim Launer directed the economics, selected priorities, supplied constraints, challenged results, decided what evidence was sufficient for each research milestone, and retained acceptance and release authority. Codex and Claude were active engineering agents rather than advisory chat systems.

Codex performed most of the foundational construction. It converted Tim's evolving requirements into rigorous quantitative and integration specifications; implemented the Python and QuantLib components; created JSON market and deal contracts; built command-line, web, MCP, and proposed REST boundaries; wrote documentation; and constructed and ran the main unit, integration, numerical, calibration, convergence, Greek, and bump-stability tests.

Claude provided a second engineering lane. It reviewed frozen Codex changes for mathematical, numerical, interface, security, and maintainability problems. More importantly, it built validation and regression extensions around the Codex-developed core. Those checks make review findings durable: they preserve accepted benchmarks, reproduce defects, and test whether later code changes disturb drift signs, calibration identities, event ordering, martingales, convergence, or risk behavior.

## Division of responsibility

| Participant or component | Primary responsibility |
|---|---|
| Tim | Economic intent, priorities, constraints, challenge questions, judgment, finding triage, residual-risk acceptance, and release decisions |
| Codex / ChatGPT | Rigorous specifications, most ground programming, QuantLib/Python integration, interfaces, documentation, test construction, execution, debugging, and evidence-backed handoff |
| Claude | Independent derivation, findings-first code review, validation extensions, regression harnesses, and additional challenge coverage for future changes |
| Mac and Git | Shared, inspectable engineering workspace containing source, specifications, prompts, diffs, tests, results, and local runtime evidence |
| QuantLib | Versioned C++ quantitative primitives, Python bindings, curves, instruments, calibration helpers, models, and numerical building blocks |
| Python | Transparent product-specific composition, diagnostics, experiment speed, web integration, and reference implementation |
| C++ | QuantLib's native implementation language and the measured path for lower latency, stronger types, concurrency, and a possible upstream-quality extension |
| Stack Overflow | Community reconnaissance for API behavior, wrapper history, and known limitations; never the final authority |
| DigitalOcean | Controlled hosted runtime with TLS, process supervision, health checks, deployment evidence, and rollback |

## The collaborative development loop

1. Tim defines or refines the economic question, scope, constraints, and acceptance criteria.
2. Codex inspects the existing repository and writes a detailed specification close to the installed QuantLib integration.
3. Codex implements the bounded change end to end and writes tests with explicit expected behavior.
4. Codex runs the tests, pricing commands, document builds, and local web checks, then reports the exact diff and evidence.
5. Claude receives a frozen change set and independently checks mathematics, cash-flow semantics, calibration, numerical stability, and interface behavior.
6. Claude reports findings first, before rewriting the implementation, so Tim can assess severity and intent.
7. Claude converts important review conclusions into validation and regression extensions around the Codex core.
8. Codex integrates accepted corrections, reruns both the original suite and Claude's new challenges, and resolves regressions.
9. The application is exercised locally on the Mac and in the DigitalOcean deployment environment.
10. Tim accepts or rejects the result and owns the remaining limitations and next priorities.

This loop deliberately produces both the software and the means to challenge it. Validation is not postponed until the end and is not limited to a prose report.

## Direct prompt-to-production operation

The practical workflow is unusually direct. Tim supplies the initiating prompt and the system can continue without manual handoffs through:

1. rigorous specification and coding;
2. local regression and quantitative validation;
3. browser-based UI testing;
4. documentation updates and compilation;
5. an optional local application run when Tim wants to inspect the result personally;
6. deployment to DigitalOcean;
7. regression and health testing in the DigitalOcean environment; and
8. a Telegram notification confirming that the complete chain finished.

The notification is the last observable event, not the evidence itself. Completion means the recorded commands, tests, browser checks, deployment checks, and remote regressions have succeeded. Telegram orchestration and credentials remain external to this repository.

## A serious hobby on a seven-dollar platform

The DigitalOcean droplet costs approximately USD 7 per month, making continuous hosting easy to justify as a hobby expense. Low cost does not mean casual engineering. The application still uses TLS termination, a loopback WSGI server, systemd supervision, restricted environment files, deterministic deployment steps, health checks, regression testing, and rollback.

That combination is part of the project's appeal: frontier-style agent collaboration and sophisticated quantitative finance do not require a large organization or expensive infrastructure to become tangible. A Mac, two coding agents, open-source QuantLib, Python, selective C++, Git, and a small cloud host are enough to support serious and reproducible work.

## Evidence hierarchy

The framework uses several evidence lanes because no model, source, or test is sufficient alone:

1. Economic definitions and independently derived equations.
2. Current, version-pinned QuantLib C++ source and Python binding behavior.
3. Official library and vendor documentation.
4. Minimal executable reproductions and analytic limiting cases.
5. Unit, integration, calibration, martingale, convergence, Greek, and bump-stability tests.
6. Frozen benchmark deals, seeds, diagnostics, and stored results.
7. Cross-model review and disagreement analysis.
8. Local web, CLI, and MCP smoke tests on the Mac.
9. DigitalOcean service, TLS, environment, and rollback checks.

Stack Overflow and similar community material belong between discovery and verification. For example, discussions can reveal changed calibration-helper names, missing curve handles, curve-horizon errors, or historic multi-curve engine limitations. Because answers may refer to old QuantLib releases or incomplete product contexts, the project checks them against the installed version, upstream source or official documentation, and a runnable test before relying on them.

## Why Codex specifications matter

The specifications were not decorative documents written after the code. They established the domestic measure, FX quotation, foreign quanto sign, log-FX Itô term, curve roles, calibration objectives, cancellable cash-flow semantics, exercise event ordering, LSM targets, result schemas, validation thresholds, and interface boundaries before or alongside implementation.

That specification-first work allowed Claude to challenge a stable target rather than infer intent from code. It also made the Python reference implementation suitable for later C++ work: the economic and numerical contract can remain fixed while implementation details change.

## Why Claude's extensions matter more than a one-time review

A code review can identify a defect, but a regression test prevents the same class of defect from silently returning. Claude's strongest contribution was therefore not merely commenting on Codex output. It was surrounding that output with additional validation logic and repeatable regressions.

This approach supports future development in three ways:

- New Codex changes can be checked against an independently authored challenge suite.
- C++ migration can be compared with the Python reference under identical deals, markets, seeds, and tolerances.
- Future QuantLib extensions can preserve observable behavior while improving performance or native integration.

## Boundaries and best practices

- Keep human ownership explicit. Agents can construct and challenge; Tim decides economics, scope, accepted findings, and release.
- Give the builder and reviewer distinct roles and, when practical, separate context so the reviewer derives rather than paraphrases.
- Freeze the exact commit, market JSON, deal JSON, seeds, tolerances, and requested outputs used for review.
- Require findings to include severity, file and line, failure mechanism, and executable evidence.
- Turn every accepted material defect into a regression test.
- Record model/provider, prompts, permissions, commands, exit codes, and known limitations sufficiently for later reproduction.
- Keep secrets outside prompts and source control; grant edit, shell, network, deployment, commit, and push authority only when necessary.
- Treat cross-model agreement as broader challenge coverage, not proof, a dual bound, or formal independent model approval.
- Use Python for transparency and rapid validation; move only measured bottlenecks or stable native abstractions into C++.
- Treat deployment as part of validation: the hosted environment must pass the same critical quantitative suite plus service and health checks.

## The broader lesson

The callable XCCY engine is a demanding demonstration because it combines cross-currency cash flows, collateral-consistent curves, correlated rate and FX dynamics, calibration, simulation, and optimal stopping. Yet the reusable asset is the engineering method: one person directing two complementary coding agents across rigorous specification, implementation, independent challenge, regression protection, local execution, and hosted operation.

The result is not “AI wrote some code.” It is an emerging quantitative-engineering organization in miniature: human judgment, agent construction, agent challenge, open-source numerical infrastructure, community reconnaissance, reproducible evidence, controlled deployment, and an automated completion signal working as one system. It remains a hobby, but the work is intentionally serious and rigorous.

## Reference guidance

- [OpenAI Codex use cases](https://learn.chatgpt.com/use-cases): codebase understanding, testing, difficult-problem iteration, and change review.
- [OpenAI Codex code review](https://learn.chatgpt.com/docs/code-review): scoped review of commits and diffs with actionable findings.
- [Claude Code GitHub Actions](https://docs.anthropic.com/en/docs/claude-code/github-actions): automated review workflows and repository-specific review criteria.
- [Claude Code security](https://docs.anthropic.com/en/docs/claude-code/security): permissions, review responsibility, and untrusted-content precautions.
- [Stack Overflow QuantLib questions](https://stackoverflow.com/questions/tagged/quantlib-swig): useful implementation reconnaissance that must be version-checked.
