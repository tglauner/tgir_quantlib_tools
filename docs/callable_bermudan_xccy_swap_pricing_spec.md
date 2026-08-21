# Callable Bermudan Cross-Currency Interest-Rate Swap Pricing Specification

Status: proposed specification - no implementation
Audience: quantitative developers, model validators, trading-system integrators
Last updated: 2026-08-14

## 1. Executive decision

Price the product with a three-factor Monte Carlo model and a two-pass Longstaff-Schwartz least-squares Monte Carlo (LSM) exercise algorithm:

1. one Hull-White one-factor short-rate model for the domestic currency;
2. one Hull-White one-factor short-rate model for the foreign currency; and
3. one lognormal Black-Scholes diffusion for the FX rate, correlated with both rate factors.

This is a Monte Carlo model, not the short-rate lattice currently used by the repository's single-currency Bermudan swaptions. That lattice uses Hull-White 1F by default and also supports a G2++ comparison. A multidimensional cross-currency lattice is possible in principle, but it is not the recommended integration: it is harder to build, calibrate, and converge, and QuantLib's `TreeSwaptionEngine` accepts one short-rate model and one `Swaption` rather than a callable cross-currency cash-flow portfolio.

The existing QuantLib integration remains the benchmark and supplies conventions, curves, schedules, Hull-White calibration patterns, and regression tests. The new pricer should be a separate engine so the current `ql.TreeSwaptionEngine` results remain unchanged.

## 2. Product definition and sign convention

### 2.1 Currencies and FX quotation

- `DOM` is the reporting, collateral, and NPV currency in the first implementation.
- `FOR` is the other leg currency.
- `S(t)` is quoted as units of `DOM` per one unit of `FOR`. A `FOR` cash flow `CF_FOR` paid at time `t` is worth `S(t) * CF_FOR` in `DOM` on that path.
- All signed cash flows are from the option holder's perspective: receipts are positive and payments are negative.

### 2.2 Underlying swap

The underlying contains two independently scheduled legs plus optional notional exchanges:

- a domestic fixed, term-floating, or compounded-overnight leg;
- a foreign fixed, term-floating, or compounded-overnight leg;
- optional initial and final notional exchanges;
- optional mark-to-market FX-reset notionals, explicitly out of scope for the first implementation unless selected as a separate product variant; and
- spreads, gearing, stubs, payment lags, calendars, day counts, and business-day conventions on each leg.

The first supported trade should be a constant-notional cross-currency swap with optional initial/final exchanges. Do not silently interpret a mark-to-market cross-currency swap as constant-notional.

### 2.3 Callable versus enterable Bermudan rights

The request must carry `exercise_style`:

- `CANCEL_REMAINING_SWAP` - the holder may terminate the remaining swap on specified dates. This is the initial target.
- `ENTER_REMAINING_SWAP` - the holder may enter the remaining swap on specified dates, economically a cross-currency Bermudan swaption. This is a later compatible variant.

The request must also identify `exercise_holder` and the call settlement amount from that holder's perspective. A bare word such as "callable" is insufficient because payer/receiver and issuer/holder usages differ between systems.

For a cancellation right, exercising removes all contractually cancellable future cash flows and replaces them with the defined settlement cash flow. If the settlement is zero, a holder cancels when continuing has sufficiently negative value. For an entry right, exercising creates the remaining swap and any entry settlement.

### 2.4 Exercise event ordering

Each exercise opportunity has four dates:

- notice date;
- decision date;
- effective termination or entry date; and
- settlement date.

The trade definition must state whether coupons and notional exchanges on the effective date survive exercise. The default is: determine already-fixed coupons first, pay cash flows scheduled on or before the effective date, then remove later cancellable cash flows. No same-day ordering may be inferred from date equality alone.

For version 1, `notice_date` must equal `decision_date`; the timestamp at which notice becomes irrevocable is the information time for the exercise decision. Reject a trade with an earlier notice deadline until the state observed at that deadline and the delayed exercise mechanics are specified.

### 2.5 Decision-date cash-flow partition

For a cancellation opportunity decided at `t_i`, partition domestic-equivalent decision-date value into:

- `A_i` - cash flows that survive either decision, including coupons/notional flows through the effective date under the trade's event ordering;
- `J_i` - exercise-only settlement cash flows, converted and discounted from their actual settlement dates to `t_i`; and
- `Y_i` - cancellable cash flows and later optionality that remain only if the holder continues.

The exercise comparison excludes the common component:

```text
exercise if J_i > E[Y_i | information at t_i] + exercise_tolerance
decision-date value = A_i + max(J_i, continuation value of Y_i)
```

This partition applies even when the effective or settlement date is later than the decision date. For a zero-fee cancellation, `J_i = 0`; surviving interim flows remain in `A_i` and do not disappear. For `ENTER_REMAINING_SWAP`, define the exercise value as the state-dependent PV of the entered swap plus settlement, and compare it with the continuation value of the unexercised option.

## 3. Scope

### 3.1 In scope

- two currencies and one FX pair;
- domestic-collateral valuation in the domestic currency;
- Hull-White 1F dynamics for both short rates;
- Black-Scholes lognormal FX dynamics with deterministic piecewise FX volatility;
- a full constant 3x3 instantaneous correlation matrix, with an extension point for piecewise-constant correlation;
- deterministic notionals in each currency;
- discrete Bermudan cancellation dates;
- LSM early exercise;
- NPV, Monte Carlo error, cash-flow diagnostics, calibration diagnostics, exercise statistics, and bump-and-revalue risks; and
- reproducible results from recorded market, trade, model, and random-seed inputs.

### 3.2 Out of scope for the first implementation

- stochastic basis, stochastic volatility, local volatility, jumps, wrong-way credit risk, XVA, and funding valuation adjustments;
- collateral switching or optional collateral currency;
- mark-to-market/resettable notionals;
- multiple exercise holders, partial calls, volume choice, or exercise into an amended coupon;
- historical fixing ingestion beyond values supplied in the request;
- automatic market-data sourcing; and
- replacing the existing single-currency Bermudan tree pricer.

## 4. Required input contract

### 4.1 Trade fields

At minimum:

| Group | Required fields |
| --- | --- |
| Identity | `trade_id`, `version`, `book`, `as_of_date` |
| Product | `exercise_style`, `exercise_holder`, `reporting_currency`, `collateral_currency` |
| Domestic leg | currency, pay/receive, notional, coupon type, rate or spread, index, schedule, day count, payment lag |
| Foreign leg | same fields independently |
| FX | pair, quote direction, spot, initial exchange rule, final exchange rule |
| Exercise | notice/decision/effective/settlement dates, settlement amount and currency, same-day event order |
| Fixings | index name, fixing date, value, source timestamp |

Validation must reject inconsistent pay/receive signs, duplicate exercise dates, exercise after maturity, missing historical fixings, unsupported FX quote direction, and schedules that extend beyond the relevant curves.

### 4.2 Market fields

- domestic discount curve and any distinct domestic forecast curve;
- foreign discount curve and any distinct foreign forecast curve;
- cross-currency basis incorporated consistently in curves or explicit collateralized FX forwards;
- domestic normal swaption-volatility surface;
- foreign normal swaption-volatility surface;
- FX spot and Black volatility term structure;
- correlations `rho_dom_for`, `rho_dom_fx`, and `rho_for_fx`; and
- quote timestamps, market snapshot ID, source IDs, units, and stale-data flags.

The correlation matrix must be symmetric, have ones on the diagonal, and be positive semidefinite. Reject it if materially invalid; a small documented eigenvalue floor may repair rounding noise only, and the result must disclose that repair.

### 4.3 Model and numerical fields

- fixed or calibrated Hull-White mean reversions and volatility parameterization for each currency;
- calibration helper set and calibration error type;
- FX volatility interpolation/extrapolation rule;
- correlation source and effective date;
- training-path count, pricing-path count, time steps, seed, RNG type, antithetic flag, and optional Sobol settings;
- regression basis ID, degree, regularization, standardization rule, and candidate-path rule; and
- requested risk scenarios and bump sizes.

## 5. Market construction and calibration

### 5.1 Curves

Build each currency's discount and forecast curves from instruments appropriate to that currency and collateral agreement. The current `build_sofr_curve()` is the domestic USD template: it uses an overnight deposit at the front and SOFR OIS helpers beyond it. Generalize the pattern only when implementation begins; do not force non-USD markets through `ql.Sofr`.

Cross-currency valuation must be internally arbitrage-consistent. In particular, the domestic and foreign discount curves, spot FX, collateral convention, cross-currency basis, and model-implied FX forwards must agree within tolerance. A deterministic non-callable cross-currency swap is the mandatory first calibration check.

The first model has one stochastic rate factor per currency and no stochastic basis. The market snapshot must therefore supply:

- the domestic collateral discount curve `P_d(0,T)`;
- a foreign effective curve `P_f_star(0,T)` consistent with domestic collateral, cross-currency basis, spot FX, and collateralized FX forwards; and
- any distinct index forecast curve as a deterministic basis mapping to the corresponding modeled discount curve.

For a forecast curve `P_c_fwd`, freeze the initial multiplicative basis ratio in version 1:

```text
B_c(0,T) = P_c_fwd(0,T) / P_c_disc(0,T)
P_c_fwd(t,T) = P_c_disc(t,T) * B_c(0,T) / B_c(0,t)
```

Floating coupons derive from `P_c_fwd(t,T)`. This makes the multi-curve assumption explicit: rate uncertainty comes from the currency's Hull-White factor, while forecast/discount and cross-currency basis are deterministic. A stochastic-basis model is a different model version.

### 5.2 Hull-White calibration

Calibrate a separate `ql.HullWhite` model to each currency's normal swaption surface. Stay close to the existing repository pattern:

- create `ql.SwaptionHelper` objects with normal-volatility quotes;
- use `ql.JamshidianSwaptionEngine` for helper valuation;
- use `ql.LevenbergMarquardt` and explicit end criteria;
- fix or calibrate mean reversion according to the model configuration; and
- report market value, model value, and calibration error for every helper.

For the first benchmark, use a diagonal strip aligned to the trade's exercise dates and remaining maturity, as `bermudan_diagonal_calibration_pillars()` does today. Production validation should also compare against a broader surface calibration so a diagonal-only fit does not hide off-strip instability.

### 5.3 FX calibration

Represent FX volatility with QuantLib `BlackVolTermStructure` objects, starting with piecewise-constant ATM Black volatilities. "Black-Scholes FX" here means a lognormal FX diffusion. Because interest rates are stochastic, it does not mean that the complete product has the deterministic-rate analytic Black-Scholes price.

Use market Black implied volatilities as initial targets, not automatically as the hybrid diffusion coefficients. Calibrate the piecewise `sigma_fx(t)` buckets by pricing the same FX vanilla instruments in the two-rate-plus-FX hybrid model, then solve until model prices or re-implied Black volatilities meet section 11.2. Use the same spot, effective curves, delta, premium, and quote conventions as the trading system.

### 5.4 Correlations

Correlations are model inputs, not calibration leftovers. Source them from a governed historical/implied process, record observation windows and transformations, and provide stress values. At minimum report price sensitivity to each correlation and to a joint correlation stress.

## 6. Joint dynamics

Work under the domestic risk-neutral measure. Let `r_d(t)` and `r_f(t)` be the domestic and foreign short rates and let `X(t) = log(S(t))`.

Each rate follows a Hull-White 1F process fitted exactly to its modeled effective curve. Let `theta_f_for(t)` be the foreign-measure drift fitted to `P_f_star(0,T)`. With `S = DOM/FOR`, the domestic-measure form is:

```text
dr_d = [theta_d(t) - a_d r_d] dt + sigma_d(t) dW_d
dr_f = [theta_f_for(t) - a_f r_f - rho_for_fx sigma_f(t) sigma_fx(t)] dt
       + sigma_f(t) dW_f
```

FX follows a Black-Scholes lognormal process under the domestic measure:

```text
dS / S = [r_d - r_f] dt + sigma_fx(t) dW_fx
```

The Brownian increments satisfy the configured 3x3 correlation matrix. The displayed quanto term assumes the stated FX quotation, domestic money-market numeraire, scalar factor loadings, and the sign convention above. The implementation must derive and unit-test the drift from those conventions; changing the FX orientation or numeraire changes the formula. It is not valid to simulate an unadjusted foreign-measure Hull-White process independently and then attach FX afterward.

The implementation must document the exact numeraire and FX quote convention in code and model metadata. Martingale tests must verify discounted domestic assets and the domestic value of foreign money-market/zero-coupon assets within Monte Carlo error.

## 7. Simulation design

### 7.1 Time grid

The grid must contain every fixing, accrual boundary needed by the payoff, payment, notional exchange, notice, decision, effective exercise, and settlement date. Add intermediate steps so no interval exceeds the configured maximum, initially one month. OIS coupons should use QuantLib's compounded-overnight cash-flow conventions or a validated conditional approximation; do not simulate every overnight fixing unless the accuracy test proves it necessary.

### 7.2 Path generation

- use exact conditional Gaussian transitions for the Hull-White factors where available;
- use a log update for FX so simulated FX stays positive;
- correlate independent normal draws with a Cholesky or eigen factorization of the validated correlation matrix;
- integrate short rates consistently for pathwise domestic discount factors;
- use antithetic paths initially and optionally Brownian bridge plus Sobol after pseudo-random validation; and
- split training and pricing samples so the same paths do not both fit and value the stopping rule.

QuantLib 1.41 in the current Python environment exposes `ql.HullWhiteProcess`, `ql.BlackScholesMertonProcess`, `ql.StochasticProcessArray`, and `ql.GaussianMultiPathGenerator`. Do not simply place two independent rate processes and `ql.BlackScholesMertonProcess` in an array: that does not automatically create the pathwise `r_d-r_f` FX drift or the foreign-rate quanto adjustment. Use an explicit joint evolver (or custom QuantLib process) whose transition equations implement section 6; QuantLib's grids, random sequences, correlations, curve objects, and statistics remain reusable.

### 7.3 Pathwise cash-flow value

On each path:

1. generate both rate factors, log FX, and domestic discount factors;
2. determine all already-fixed and simulated floating coupons without look-ahead;
3. convert each foreign payment to domestic currency at the contractually applicable FX rate on that path;
4. include or exclude notional exchanges exactly as the trade specifies;
5. apply call event ordering; and
6. discount realized domestic-equivalent cash flows to the valuation date.

At an exercise date, the state-dependent value of remaining legs should use analytic Hull-White conditional zero-coupon bond prices for `P_d` and `P_f_star` where possible. Distinct forecast bonds come from the deterministic basis mapping in section 5.1. This reduces inner simulation and keeps the method a single outer Monte Carlo with regression, not a slow nested Monte Carlo.

## 8. Early exercise decision

### 8.1 Decision rule

For each alive path `p` and exercise date `t_i`, define exclusive decision components as in section 2.5:

- `E_i(p)` - exercise-only value (`J_i` for cancellation, or entered-swap value plus settlement for entry); and
- `C_i(p)` - the conditional expected value of the mutually exclusive continuation cash flows and later optionality, estimated by regression.

Exercise when:

```text
E_i(p) > C_i(p) + exercise_tolerance
```

Use a deterministic tie rule: continue when the values are equal within tolerance. Add the common surviving component `A_i` after the decision comparison. For a zero-fee cancellation, `E_i = J_i = 0`; the holder cancels when the estimated value of cancellable continuation cash flows and later optionality is negative enough.

### 8.2 Backward Longstaff-Schwartz algorithm

1. Simulate training paths and compute terminal values.
2. Starting from the last call date, regress the discounted realized value from continuing on state variables observed at that date.
3. Compare `E_i` with the fitted `C_i` and replace the future path value with the exercise value when the decision rule triggers.
4. Move one call date backward and repeat using only information available at that date.
5. Freeze all preprocessing, coefficients, and exercise rules.
6. Simulate an independent pricing sample, apply the frozen policy, and average discounted stopped cash flows.

This is the same economic comparison performed by a tree during backward induction, but the conditional continuation value is estimated from simulated cross-currency states rather than read from lattice nodes.

### 8.3 Regression state and basis

Initial standardized state variables:

- domestic Hull-White factor or short rate;
- foreign Hull-White factor or short rate;
- `log(S)`;
- domestic value of the remaining non-callable swap;
- remaining domestic-leg PV;
- domestic value of remaining foreign-leg PV; and
- time to final maturity.

Initial basis: constant, linear terms, squares, and pairwise cross-products. Prefer orthogonal polynomials after standardization and cap the basis at a predeclared size. Record rank, condition number, coefficient vector, training count, and out-of-sample residual diagnostics at every exercise date. If regression is ill-conditioned or under-populated, fail with a diagnostic or use a preapproved simpler basis; never silently return an exercise-always rule.

Use all alive paths for a cancellation right unless validation supports a narrower candidate set. The ordinary "in-the-money paths only" shortcut is not directly applicable when the immediate cancellation payoff is zero and the economic benefit is avoiding a negative continuation value.

## 9. QuantLib integration plan

### 9.1 Reuse from this repository

Preserve and reuse these design patterns when implementation is authorized:

- `valuation_date()` and the single evaluation-date discipline;
- explicit calendars, business-day handling, schedules, day counts, and spot starts;
- OIS construction and calibration repricing checks from `build_sofr_curve()`;
- `ql.SwaptionHelper` construction and normal-vol conversions;
- Hull-White calibration and parameter reporting from `build_bermudan_short_rate_model()`;
- trade-state normalization, structured result rows, deterministic defaults, and bump-and-revalue reporting; and
- unit-test style in `tests/test_sofr_curve.py`.

### 9.2 Do not reuse as the cross-currency engine

- `ql.Swaption` represents a single underlying swaption, not this two-currency callable cash-flow set.
- `ql.TreeSwaptionEngine` is a short-rate lattice engine for swaptions. It does not evolve two currency curves plus FX.
- a single domestic Hull-White tree with deterministic FX forwards omits foreign-rate and FX/rate correlation risks and is only an approximation/control, not the specified model.

### 9.3 Python reference versus C++ production

QuantLib's C++ library provides generic Monte Carlo and Longstaff-Schwartz infrastructure, but the installed Python 1.41 wrapper does not expose a generic `LongstaffSchwartzPathPricer`, and neither the installed package nor the current repo has a callable cross-currency instrument. Therefore:

- build the first transparent reference pricer in this repository with QuantLib market/process objects and an explicit, testable LSM layer only after approval; and
- implement the production path pricer/engine in C++ against a pinned QuantLib version, using QuantLib cash flows, curves, processes, random sequences, regression utilities, and pricing-engine conventions.

Do not make a development branch of QuantLib itself the production dependency. The current Python environment is QuantLib 1.41. QuantLib 1.43 is the latest official release as of this specification and adds constant-notional cross-currency swap instruments, which should be evaluated for the deterministic C++ layer. It still does not supply the complete callable three-factor MC-LSM engine specified here. Pin the selected release only after compatibility and regression testing.

## 10. Outputs

Every result must include:

- NPV in reporting currency and currency unit;
- standard error and 95 percent confidence interval;
- non-callable underlying NPV;
- callable value and embedded option value under a documented sign convention;
- path counts, rejected paths, time-grid size, seed, RNG, antithetic setting, and runtime;
- model parameters, calibration rows, correlation matrix, and market snapshot ID;
- unconditional exercise probability by date, conditional exercise probability among surviving paths, no-exercise probability, and expected exercise date;
- regression diagnostics by date;
- cash-flow PV by leg and currency; and
- requested curve, volatility, FX spot, correlation, and model-parameter risks.

All values are from the unilateral exercise holder's perspective. Define `embedded_option_value = callable_value - non_callable_value`; it must be nonnegative within the comparison error defined in section 11 because the holder can always choose not to exercise. For the counterparty perspective, negate the full callable trade result or price a separately defined request with the opposite holder; do not reverse cash-flow signs while silently preserving option ownership.

## 11. Validation and acceptance criteria

For every comparison below, define `comparison_standard_error` explicitly:

- on common-random-number or otherwise paired paths, compute the pathwise payoff difference `D_p = PV_A(p) - PV_B(p)` and use `stdev(D_p) / sqrt(N)`;
- on independent samples, use `sqrt(SE_A^2 + SE_B^2)`; and
- if a more general correlated estimator is used, use `sqrt(SE_A^2 + SE_B^2 - 2 * covariance(mean_A, mean_B))` and report the covariance estimate.

Do not add marginal standard errors or ignore covariance in a paired comparison.

### 11.1 Deterministic and limiting tests

- With no call dates, equal the analytic non-callable XCCY PV within `max(3 * comparison_standard_error, 0.25 bp * domestic_notional)`.
- With FX volatility and both rate volatilities near zero, match deterministic discounted cash flows within `0.10 bp * domestic_notional`.
- With identical currencies, unit FX, identical curves, and consistent legs, reduce to the corresponding single-currency result within `max(3 * comparison_standard_error, 0.25 bp * domestic_notional)`.
- With one exercise date, match a high-accuracy European or nested-MC benchmark within `max(3 * comparison_standard_error, 0.50 bp * domestic_notional)`.
- With a prohibitively expensive exercise fee, converge to the non-callable value.
- With an immediately dominant zero-fee cancellation, the first-date conditional exercise probability must be at least 99 percent.
- `callable_value - non_callable_value` must equal the reported embedded option value and be no less than `-3 * comparison_standard_error`.

### 11.2 Martingale and calibration tests

- Reprice both OIS calibration sets to no more than `0.01 bp` par-rate error and `1e-8 * notional` absolute NPV error.
- Reprice domestic and foreign swaption helpers to no more than 10 percent relative price error per helper and 5 percent equal-weight RMS relative price error across the approved strip. For helper `i`, `e_i = V_model_i / V_market_i - 1`, and the implemented strip metric is `sqrt(sum(e_i^2) / N)`.
- Reprice FX vanilla calibration instruments to no more than `0.25` volatility percentage points of re-implied Black-vol error per quote.
- Validate domestic-measure martingales for domestic and converted foreign zero-coupon assets within three standard errors and `0.25 bp` of notional.
- Reprice a deterministic cross-currency swap against an independent cash-flow calculation within `0.10 bp * domestic_notional`.

### 11.3 Numerical convergence

Demonstrate stability across:

- at least three path counts;
- at least two time-grid densities;
- multiple independent seeds;
- simpler and richer regression bases;
- pseudo-random and, after validation, low-discrepancy sequences; and
- training/pricing sample splits.

For adjacent path-count or grid refinements, require an absolute price difference no greater than `max(3 * comparison_standard_error, 0.50 bp * domestic_notional)`. For the official pricing sample, require:

```text
standard_error <= min(
    1.00 bp * domestic_notional,
    max(0.5% * abs(embedded_option_value), 0.05 bp * domestic_notional)
)
```

Pricing-path error is conditional on the fitted exercise policy and does not include training-policy uncertainty or LSM lower-bound bias. Run at least five independent training seeds. Freeze one common pricing sample, with at least the official pricing-path count and satisfying the single-price error threshold above, and evaluate every trained policy on those identical paths. The standard deviation across these paired policy values estimates training-policy dispersion and must be no greater than `0.50 bp * domestic_notional`; report it separately from the pricing-sample standard error. Do not use independently seeded pricing samples for this test because that would mix ordinary pricing noise with policy uncertainty.

### 11.4 Independent benchmark

Model validation should compare at least one trade with an independent implementation or vendor. A simplified two- or three-dimensional PDE/lattice benchmark is useful for short maturities and sparse calls even though it is not the production engine.

## 12. Risks and controls

| Risk | Required control |
| --- | --- |
| Wrong FX quotation or sign | explicit `DOM/FOR` metadata and unit tests for conversion |
| Wrong measure/quanto drift | martingale tests and documented numeraire |
| Regression look-ahead bias | independent training and pricing paths |
| Overfitting | fixed basis policy, conditioning diagnostics, out-of-sample tests |
| Hidden curve inconsistency | deterministic XCCY repricing and FX-forward checks |
| Correlation instability | PSD validation, source metadata, bump/stress results |
| Date/event ambiguity | four-date exercise records and explicit event ordering |
| Global QuantLib evaluation date | one valuation context per job/process and concurrency tests |
| False numerical precision | standard error, convergence report, rounded display |

## 13. Proposed implementation sequence - future work only

1. Freeze the trade and market schemas and build a deterministic non-callable XCCY cash-flow pricer.
2. Add both calibrated Hull-White models and FX vanilla validation.
3. Add the joint domestic-measure simulator and martingale tests.
4. Add one-date exercise and an independent European benchmark.
5. Add two-pass Bermudan LSM, exercise diagnostics, and convergence tests.
6. Add common-random-number bump risks and batch performance work.
7. Port the validated engine to the C++ integration boundary in the companion guide.

No phase may start by changing the existing single-currency `TreeSwaptionEngine` path.

## 14. References

- QuantLib official documentation: https://www.quantlib.org/docs.shtml
- QuantLib releases, including 1.43: https://github.com/lballabio/QuantLib/releases
- QuantLib 1.43 `TreeSwaptionEngine`: https://github.com/lballabio/QuantLib/blob/v1.43/ql/pricingengines/swaption/treeswaptionengine.hpp
- QuantLib 1.43 exercise types: https://github.com/lballabio/QuantLib/blob/v1.43/ql/exercise.hpp
- QuantLib 1.43 Longstaff-Schwartz path pricer: https://github.com/lballabio/QuantLib/blob/v1.43/ql/methods/montecarlo/longstaffschwartzpathpricer.hpp
- QuantLib 1.43 Monte Carlo base: https://github.com/lballabio/QuantLib/blob/v1.43/ql/pricingengines/mcsimulation.hpp
- Longstaff, F. A. and Schwartz, E. S. (2001), "Valuing American Options by Simulation: A Simple Least-Squares Approach," Review of Financial Studies 14(1), 113-147.

## Rollback

This is a specification only. Removing this Markdown file and its generated PDF fully rolls back the change; application behavior and pricing results are unaffected.
