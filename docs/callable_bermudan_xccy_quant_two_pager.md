# Callable Bermudan Cross-Currency Swap - Quantitative Model Summary

Status: generic quantitative specification
Model: two Hull-White rate factors + lognormal FX + Bermudan LSM
Numeraire: domestic money-market account; values reported in domestic currency

## 1. Product and notation

Consider a two-currency swap with domestic (`DOM`) and foreign (`FOR`) cash-flow legs, optional initial/final notional exchanges, and exercise dates `t_1 < ... < t_M`. Let

- `S(t)` be FX in units of `DOM` per one unit of `FOR`;
- `P_d(t,T)` be the domestic collateral discount bond;
- `P_f*(t,T)` be the foreign effective discount bond consistent with the domestic collateral convention and cross-currency basis; and
- positive cash flows denote receipts by the exercise holder.

A foreign cash flow `CF_f(T)` has pathwise domestic value `S(T) CF_f(T)`. All cash flows are discounted with the domestic numeraire.

For a cancellation right decided at `t_i`, partition value into:

- `A_i`: cash flows common to exercise and continuation, including surviving flows through a delayed effective date;
- `J_i`: exercise-only settlement value at `t_i`; and
- `Y_i`: cancellable future cash flows and later optionality if the trade continues.

The holder exercises when

```text
J_i > E^Qd[Y_i | F(t_i)] + epsilon_ex
```

and the decision-date value is `A_i + max(J_i, C_i)`, where `C_i` is the conditional continuation estimate. For a zero-fee cancellation, `J_i = 0`: the holder cancels when continuation is negative. For an option to enter the swap, replace `J_i` by the state-dependent PV of the entered swap plus settlement.

## 2. Joint stochastic model

Work under the domestic risk-neutral measure `Q_d`. Each currency has a Hull-White one-factor short rate and FX is lognormal. With `S = DOM/FOR`:

```text
dr_d = [theta_d(t) - a_d r_d] dt + sigma_d(t) dW_d

dr_f = [theta_f(t) - a_f r_f
        - rho_fS sigma_f(t) sigma_S(t)] dt + sigma_f(t) dW_f

dS/S = [r_d - r_f] dt + sigma_S(t) dW_S
```

`theta_d` fits the domestic curve under `Q_d`. Calibrate the foreign Hull-White curve fit under its foreign/effective numeraire measure, then transform its dynamics to `Q_d`; the displayed negative quanto drift is that measure change for the stated quotation. Equivalently, verify the domestic-measure identity `S(0) P_f*(0,T) = E^Qd[D_d(0,T) S(T)]`. Changing numeraire or reversing the FX quotation changes the adjustment and requires a fresh derivation.

The instantaneous Brownian correlation matrix is

```text
        [ 1          rho_df      rho_dS ]
R   =   [ rho_df     1           rho_fS ]
        [ rho_dS     rho_fS      1      ]
```

`R` must be symmetric and positive semidefinite. A constant matrix is the base model; piecewise-constant correlation is an extension. FX is Black-Scholes only in its diffusion form: stochastic rates make the full hybrid model non-analytic.

### Multi-curve assumption

The base model has one stochastic rate factor per currency and deterministic forecast/discount basis. If `P_c^F` is a forecast pseudo-discount curve and `P_c^D` the modeled discount curve, freeze

```text
B_c(0,T) = P_c^F(0,T) / P_c^D(0,T)
P_c^F(t,T) = P_c^D(t,T) B_c(0,T) / B_c(0,t).
```

Forward coupons are derived from `P_c^F(t,T)`. Stochastic cross-currency or tenor basis requires another factor and is outside this model.

## 3. Calibration

- **Curves:** bootstrap domestic collateral and foreign effective curves from liquid deposits/OIS/basis instruments. Enforce `F_FX(0,T) = S(0) P_f*(0,T) / P_d(0,T)` and reprice calibration instruments.
- **Domestic HW:** calibrate to domestic normal-vol swaptions on the exercise diagonal. Fix or tightly constrain `a_d`; regularize/bound piecewise `sigma_d(t)` to avoid an unstable joint fit.
- **Foreign HW:** apply the analogous foreign swaption fit and identification constraints for `a_f` and `sigma_f(t)`.
- **FX diffusion:** fit piecewise `sigma_S(t)` to selected ATM/benchmark-tenor FX vanillas in the full stochastic-rate hybrid. If several strikes are used, minimize weighted price error and report smile residuals; exact smile fitting needs a local/stochastic-vol extension.
- **Correlation:** use governed historical/implied estimates, validate PSD, and report independent stresses to all three correlations.

Calibration output includes fitted parameters, market/model price per helper, relative error, optimizer status, and curve/vol/correlation snapshot identifiers. Parameter stability and out-of-sample swaption/FX-option repricing are part of model validation.

## 4. Monte Carlo discretization

The event grid contains all fixing, accrual, payment, notional-exchange, decision, effective, and settlement dates, plus intermediate steps capped at a chosen maximum interval. Simulate correlated normal increments using a Cholesky/eigen factorization of `R`.

- Use exact conditional Gaussian transitions for Hull-White factors when available.
- Integrate domestic short rates consistently to obtain pathwise discount factors.
- Update log FX with `d log S = [r_d-r_f-0.5 sigma_S(t)^2]dt + sigma_S(t)dW_S`, using a discretization consistent with the rate integrals.
- Value conditional zero-coupon bonds analytically from Hull-White states where possible; apply deterministic basis mapping for forecast curves.
- Use antithetics initially; validate Sobol/Brownian-bridge variants separately.

An independent non-callable XCCY cash-flow PV is the primary control variate and deterministic benchmark.

## 5. Bermudan exercise by least-squares Monte Carlo

Use a two-pass Longstaff-Schwartz algorithm.

**Training pass.** Simulate training paths and work backward from `t_M`. At `t_i`, the regression target is the value, discounted to `t_i`, of cancellable cash flows in `(t_i,t_{i+1}]` plus the optimized value at `t_{i+1}`. Exclude common `A_i` cash flows from both alternatives; add them outside the exercise comparison. Regress this target on state observed at `t_i`. A generic standardized basis is

```text
1, r_d, r_f, log(S), PV_d, S*PV_f,
r_d^2, r_f^2, log(S)^2, r_d*r_f, r_d*log(S), r_f*log(S).
```

Use all alive paths for a cancellation right unless a validated candidate filter is specified. Record rank, condition number, coefficients, path count, and residual diagnostics. Freeze preprocessing and coefficients after training.

**Pricing pass.** Apply the frozen policy forward on independent paths. The first exercise stops only the cancellable tail; retain already-paid and delayed/common cash flows and add the exercise settlement. Discount every realized cash flow to time zero and average. This is the LSM lower-bound estimate. Re-train across seeds and evaluate each policy on one common frozen pricing sample to separate policy dispersion from ordinary pricing noise.

## 6. Measures, risks, and validation

Core outputs are callable NPV, non-callable NPV, embedded option value, Monte Carlo standard error/confidence interval, exercise/no-exercise probabilities, expected exercise time, per-leg PV, calibration diagnostics, and regression diagnostics. From the holder perspective:

```text
embedded option value = callable NPV - non-callable NPV >= 0
```

up to covariance-aware Monte Carlo comparison error.

Risk is bump-and-revalue with common random numbers: domestic/foreign curve DV01, forecast-basis and cross-currency-basis risk, domestic/foreign swaption vega, FX delta/gamma, FX vega, three correlation sensitivities, and Hull-White parameter stresses. State whether each bump recalibrates the model and retrains the stopping policy.

Minimum validation set:

1. no exercise dates reproduce the non-callable XCCY PV;
2. zero-vol limits reproduce deterministic discounted cash flows;
3. identical currencies and unit FX reduce to a single-currency result;
4. one exercise date matches an independent European/nested-MC benchmark;
5. domestic-numeraire-discounted domestic assets and discounted FX-converted foreign assets are martingales under `Q_d`;
6. prices converge across path counts, grids, bases, and independent training seeds;
7. representative multi-exercise cases compare the LSM lower bound with a dual upper bound or trusted nested-MC benchmark; and
8. all differences use paired pathwise errors under common random numbers, or the covariance-aware error of the difference.

## References

- F. A. Longstaff and E. S. Schwartz (2001), "Valuing American Options by Simulation: A Simple Least-Squares Approach."
- QuantLib reference documentation: https://www.quantlib.org/docs.shtml
