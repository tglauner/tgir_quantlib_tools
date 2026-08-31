# LinkedIn post

I recently guided two coding agents through a project that became much larger than either its starting point or its final pricer.

The visible product is a working three-factor callable cross-currency model. The equally important result is the collaborative engineering framework that built it: me directing the economics and acceptance standard; Codex producing most of the rigorous specifications, programming, integrations, documentation, and tests; and Claude reviewing that work and building validation and regression extensions around it.

The project began with the fundamentals: curve construction, schedules, discounting, and simple swap and swaption examples through QuantLib's Python bindings. The next iterations rebuilt the USD SOFR curve around OIS instruments, added calibration residuals and tests, calibrated Hull–White and G2++ models to swaption volatility, and priced Bermudan swaptions with backward induction on a tree.

An equity cliquet then broadened the work beyond rates and introduced another useful lesson: not every product needs to be forced into a monolithic native engine. QuantLib can own mature primitives such as calendars, curves, instruments, and calibration helpers while transparent Python code owns product-specific orchestration and diagnostics.

The most interesting question was whether QuantLib natively prices a callable EUR/USD cross-currency swap. The answer is nuanced. QuantLib 1.43 provides many of the building blocks—cross-currency instruments, Hull–White models, swaption engines, and multi-process simulation utilities—but not a single engine that combines two rates factors, lognormal FX, domestic-measure quanto drift, cross-currency cash flows, and Bermudan cancellation.

The resulting extension uses:

- USD and EUR Hull–White one-factor dynamics
- Black–Scholes-style lognormal EUR/USD dynamics
- A configurable three-factor correlation matrix
- Curve and volatility calibration through QuantLib
- Exact Gaussian state transitions
- Monte Carlo valuation with two-pass Longstaff–Schwartz regression
- Independent policy-training and pricing paths
- Martingale, convergence, calibration, bump-stability, and Greek diagnostics
- JSON, CLI, web, MCP, and proposed REST integration boundaries

The benchmark is a 10-year, non-callable-for-two-years EUR ESTR versus USD fixed 4% swap. The stored research run values the callable trade near USD 8.34 million and separately reports the non-callable swap, embedded cancellation option, exercise profile, regression diagnostics, and sampling error.

The main lesson is architectural as much as quantitative: use Python to make economics, calibration, and validation inspectable; move measured bottlenecks into C++ only after the model and interfaces are stable.

The workflow was deliberately collaborative and asymmetric. I supplied direction, finance judgment, constraints, questions, and approval. Codex was the primary builder: it turned the dialogue into formal deal semantics, model dynamics, calibration objectives, Monte Carlo and LSM design, JSON contracts, Python/QuantLib code, web and MCP interfaces, deployment material, and executable tests. This was not a collection of suggested snippets; the agent performed most of the ground programming work end to end.

Claude first provided a findings-first review of frozen Codex changes. More importantly, it then developed extensions around the Codex implementation for independent validation and regression testing. Those extensions preserve benchmarks and challenge future changes for measure and drift signs, calibration, cash-flow ordering, martingales, convergence, Greeks, and bump stability. Review therefore became durable code, not a one-time opinion.

The broader toolchain mattered. The Mac was the shared engineering floor where prompts, specifications, code, diffs, tests, and logs remained visible. QuantLib contributed mature C++ primitives and Python bindings. Python kept the new hybrid model inspectable; C++ remains the path for measured performance bottlenecks and a possible rigorous QuantLib extension. Stack Overflow helped locate API history and implementation clues, but every useful answer was checked against the installed library version, upstream source or current documentation, and executable reproductions.

The same system reaches DigitalOcean: one Ubuntu droplet, Apache for TLS termination, Gunicorn on loopback, Flask and QuantLib behind it, and systemd for process ownership. Releases build a fresh virtual environment at the final path, keep secrets in a restricted server-side environment file, run both loopback and public health checks, and retain a rollback copy. Hosting is another evidence lane for the agent-built application, not an afterthought.

And the cost makes me smile: the DigitalOcean droplet is about $7 per month. This is absolutely a hobby—but a serious, rigorous one that is easy to keep online.

The workflow is remarkably direct. I provide the prompt; the system can continue through specification, coding, regression tests, browser UI tests, documentation, an optional local run, DigitalOcean deployment, regression testing again on the droplet, and finally a Telegram message telling me it is all done. The notification is not the proof—the captured tests and deployment evidence are—but it is a delightful final signal that the complete chain finished.

This is a research and learning platform—not a claim of production model approval. But the breadth of the human–Codex–Claude collaboration is as significant as the mathematical breadth of the pricer. It provides a repeatable way to extend QuantLib rigorously: specification, implementation, tests, independent challenge, regression protection, local proof, hosted proof, and accountable human acceptance.

#QuantLib #Python #Cpp #QuantFinance #Derivatives #MonteCarlo #HullWhite #FX #ModelValidation #FinancialEngineering
