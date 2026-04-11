# Research Notes

## Swaption Pricing

### Repo-relevant modeling takeaways
- The repo's European swaption calibrates `ql.HullWhite` to the selected ATM normal-vol matrix pillar and prices with `ql.JamshidianSwaptionEngine`.
- The repo's Bermudan swaption calibrates either `ql.HullWhite` or `ql.G2` to a diagonal ATM strip built from the fixed-final-maturity call schedule and prices with `ql.TreeSwaptionEngine`.
- QuantLib's Jamshidian engine documentation explicitly points to Peter Caspers' note on start-delay handling, and the broader one-factor Gaussian / Markov-functional implementation papers remain directly relevant to the repo's short-rate calibration workflow.

### QuantLib-linked swaption references
1. Peter Caspers (2013), [Jamshidian Swaption Formula Fine Tuned](https://ssrn.com/abstract=2246054).
2. Peter Caspers (2013), [One Factor Gaussian Short Rate Model Implementation](https://www.econbiz.de/10013083737).
3. Peter Caspers (2013), [Markov Functional One Factor Interest Rate Model Implementation in QuantLib](https://www.deriscope.com/docs/Markov_Functional_Peter_Caspers_2013.pdf).

### Foundational European and Bermudan swaption papers
1. Farshid Jamshidian (1989), [An Exact Bond Option Formula](https://doi.org/10.1111/j.1540-6261.1989.tb02413.x).
2. Leif B. G. Andersen (1999), [A Simple Approach to the Pricing of Bermudan Swaptions in the Multi-Factor LIBOR Market Model](https://ssrn.com/abstract=155208).
3. Francis A. Longstaff, Pedro Santa-Clara, Eduardo S. Schwartz (2001), [Throwing Away a Billion Dollars: The Cost of Suboptimal Exercise Strategies in the Swaptions Market](https://doi.org/10.1016/S0304-405X(01)00073-3).

## Equity Cliquet Pricing

### Repo implementation choice
- The new SPX trade uses QuantLib's `ql.CliquetOption` with `ql.AnalyticCliquetEngine`.
- The market stack is `SPX spot + flat dividend yield + SOFR discount curve + flat Black vol`.
- The editor page adds reset-by-reset decomposition, analytic Greeks, a deterministic spot/vol scenario grid, and a Monte Carlo payoff distribution.

### Ten equity cliquet references
1. Heather A. Windcliff, Peter A. Forsyth, Kenneth R. Vetzal (2006), [Numerical Methods and Volatility Models for Valuing Cliquet Options](https://www.tandfonline.com/doi/full/10.1080/13504860600839964).
2. Carole Bernard, Phelim P. Boyle, William Gornall (2011), [Locally-Capped Investment Products and the Retail Investor](https://researchportal.vub.be/en/publications/locally-capped-investment-products-and-the-retail-investor/).
3. Carole Bernard, Wei Li (2013), [Pricing and Hedging of Cliquet Options and Locally-Capped Contracts](https://researchportal.vub.be/en/publications/pricing-and-hedging-of-cliquet-options-and-locally-capped-contrac/).
4. Fiodar Kilin, Morten Nalholm, Uwe Wystup (2014), [Numerical Experiments on Hedging Cliquet Options](https://researchprofiles.ku.dk/da/publications/numerical-experiments-on-hedging-cliquet-options/).
5. Geng Deng, Tim Dulaney, Craig McCann, Mike Yan (2017), [Efficient Valuation of Equity-Indexed Annuities Under Levy Processes Using Fourier-Cosine Series](https://www.risk.net/journal-of-computational-finance/5316511/efficient-valuation-of-equity-indexed-annuities-under-levy-processes-using-fourier-cosine-series).
6. Ralf Korn, Busra Zeynep Temocin, Jorg Wenzel (2017), [Applications of the Central Limit Theorem for Pricing Cliquet-Style Options](https://publica.fraunhofer.de/entities/publication/b0fc0ae7-213e-4bfc-bb8e-1320a298cb21).
7. Zhenyu Cui (2017), [Equity-Linked Annuity Pricing with Cliquet-Style Guarantees in Regime-Switching and Stochastic Volatility Models with Jumps](https://doi.org/10.1016/j.insmatheco.2017.02.010).
8. Markus Hess (2018), [Cliquet Option Pricing with Meixner Processes](https://www.vmsta.org/journal/VMSTA/article/107).
9. Markus Hess (2018), [Cliquet Option Pricing in a Jump-Diffusion Levy Model](https://www.vmsta.org/journal/VMSTA/article/118/read).
10. Yaqin Feng, Min Wang, Yuanqing Zhang (2019), [CVA for Cliquet Options Under Heston Model](https://doi.org/10.1016/j.najef.2019.02.008).

## QuantLib note
- QuantLib's cliquet test suite validates the analytic cliquet engine against an example from Espen Gaarder Haug's option-pricing formulas book. That is a validation source, but not counted above because the list here is limited to research papers and related technical papers.
