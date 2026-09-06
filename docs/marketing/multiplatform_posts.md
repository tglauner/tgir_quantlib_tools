# Multi-platform launch post drafts

These drafts present TGIR QuantLib Tools as a transparent research and educational project. They intentionally avoid describing it as a production-approved pricing model.

## X - Done 9/1/26

I built a transparent Python + QuantLib derivatives lab: SOFR curves, swaps, European and Bermudan swaptions, an SPX cliquet, and a callable EUR/USD cross-currency swap with Monte Carlo + Longstaff-Schwartz.

Try it: https://quant.tglauner.com/

#QuantLib #QuantFinance

### Optional reply

The callable XCCY model combines Hull-White rates, lognormal FX, exact joint Gaussian simulation, and a two-pass exercise policy. The repo includes calibration, martingale, convergence, sensitivity, and regression checks:

https://github.com/tglauner/tgir_quantlib_tools

Research and education only; not a production-approved model.

## Stack Overflow

Stack Overflow is not an appropriate venue for a product announcement. If this addresses a real implementation problem that is not already answered on the site, use the technical, self-answered version below. Search for duplicates first, include a minimal reproducible example, disclose the project affiliation, and omit the live-demo and course promotion.

### Question title

How can I structure a callable cross-currency swap pricer when QuantLib has no native hybrid engine?

### Question body

I am implementing a constant-notional callable EUR/USD cross-currency swap in Python. The deal receives quarterly compounded EUR €STR, pays semiannual USD fixed, exchanges notionals, and has annual cancellation dates after a two-year no-call period. USD is the collateral and reporting currency.

QuantLib gives me the components I need for dates, calendars, OIS curves, swaption helpers, Hull-White calibration, and benchmark swaption engines, but not one native engine combining two short-rate factors, FX, cross-currency cash flows, and Bermudan cancellation.

My intended architecture is:

1. Bootstrap separate USD and EUR OIS curves.
2. Calibrate one-factor Hull-White models to each ATM swaption surface.
3. Calibrate a piecewise-constant lognormal EUR/USD volatility term structure.
4. Simulate the two rate states and FX jointly under the USD money-market measure.
5. Convert EUR cash flows pathwise into USD and discount all cash flows with the simulated USD bank account.
6. Estimate the cancellation policy with Longstaff-Schwartz regression.

What are the key modeling and implementation details needed to keep this decomposition internally consistent, especially the foreign-rate drift in FX, correlated simulation, and separation of training and pricing paths?

Disclosure: I maintain an open-source research implementation of this approach. The relevant code is in `standalone_xccy_pricer.py` at https://github.com/tglauner/tgir_quantlib_tools.

### Self-answer

The decomposition works, but three details are essential.

First, simulate under one measure consistently. With EUR/USD quoted as USD per EUR and the USD money-market account as numeraire, the FX drift must include the domestic-minus-foreign short-rate term and the foreign-rate quanto adjustment implied by the chosen correlations. Omitting that adjustment generally breaks discounted-FX martingale tests.

Second, preserve the full joint covariance of the two Hull-White state increments and the FX Brownian increment. Drawing independent shocks and correlating only endpoint values is not equivalent. For piecewise-constant parameters, integrate the covariance over each time step and sample the resulting Gaussian vector. This also makes zero-volatility and exact-variance limit tests practical.

Third, split Longstaff-Schwartz into two passes. Fit continuation regressions backward on a training sample, freeze the exercise policy, and value that policy on an independently seeded pricing sample. Reusing the training paths for the reported value introduces in-sample bias and makes validation harder.

The implementation should also verify:

- OIS and swaption calibration residuals;
- domestic discount-factor, discounted-FX, and FX-converted foreign-bank-account martingales;
- callable value identities and exercise-probability conservation;
- path-count convergence with independent samples; and
- common-random-number bump-and-revalue sensitivities with half-bump stability.

This produces a transparent research implementation, not a model ready for production use. Important remaining limitations can include deterministic basis, ATM-only FX volatility, simplified rate volatility, and the absence of an independent upper-bound estimator for the Bermudan feature.

## Facebook

I have been building a transparent derivatives pricing and model-validation lab with Python and QuantLib, and the latest version is ready to explore.

The workstation now brings together:

- SOFR curve construction and calibration repricing
- interest-rate swaps and European and Bermudan swaptions
- an SPX equity cliquet with scenarios and payoff diagnostics
- a callable EUR/USD cross-currency swap model using Hull-White rates, lognormal FX, Monte Carlo, and Longstaff-Schwartz regression
- calibration, martingale, convergence, sensitivity, sanity, and regression checks

The goal is not to present another black box. It is to make the market mechanics, model assumptions, numerical methods, and validation evidence visible in one research and learning environment.

Try the live workstation:
https://quant.tglauner.com/

Explore the open-source code:
https://github.com/tglauner/tgir_quantlib_tools

For structured learning, my courses cover interest-rate derivatives and MBS/ABS in depth:

https://tglauner.com/mastering_interest_rate_derivatives/?utm_source=facebook&utm_medium=organic&utm_campaign=quantlib_tools

https://tglauner.com/mastering_mbs_and_abs/?utm_source=facebook&utm_medium=organic&utm_campaign=quantlib_tools

This is a research and educational platform, not a production-approved or independently validated bank model.

#QuantLib #Python #QuantFinance #Derivatives #ModelValidation

## Instagram

What does a derivatives model look like when the assumptions and validation checks are visible?

I built a Python + QuantLib research lab that moves from SOFR curves and vanilla swaps to European and Bermudan swaptions, an SPX equity cliquet, and a callable EUR/USD cross-currency swap.

The callable model combines two Hull-White rate factors, lognormal FX, correlated Monte Carlo simulation, and a two-pass Longstaff-Schwartz exercise policy. It is challenged with calibration, martingale, convergence, sensitivity, and regression tests.

The point is transparency: show the market inputs, model mechanics, numerical choices, exercise behavior, and limitations—not just one price.

Live demo and source code:
quant.tglauner.com
github.com/tglauner/tgir_quantlib_tools

Research and education only. This is not a production-approved model.

#QuantLib #Python #QuantFinance #Derivatives #InterestRates #MonteCarlo #ModelValidation #FinTech

### Suggested carousel

1. Cover: "Inside a transparent derivatives pricing lab"
2. Dashboard overview
3. SOFR curve and OIS repricing
4. Bermudan swaption calibration and call schedule
5. Callable EUR/USD model and exercise probabilities
6. Validation checks: calibration, martingales, convergence, and Greeks
7. Closing: live demo, GitHub repository, and research-use disclaimer

Use the existing screenshots in `docs/assets/user-guide/` for slides 2–4. Capture fresh callable-XCCY screenshots for slides 5–6 before publishing so the visuals match the current application.

## Publishing checklist

- Confirm that `https://quant.tglauner.com/` is live and that any intended demo credentials work.
- Add the demo URL to the Instagram bio before using the phrase "link in bio"; the draft above does not assume that setup.
- Preview every image on mobile and remove any account details or sensitive market data.
- Keep the research-use disclaimer on every platform.
- For Stack Overflow, post only when the question reflects a genuine programming problem and survives a duplicate search.
