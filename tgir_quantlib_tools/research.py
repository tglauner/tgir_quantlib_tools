SWAPTION_RESEARCH_SECTIONS = [
    {
        "title": "QuantLib-Linked Swaption References",
        "intro": (
            "These are the papers and notes most directly tied to the QuantLib swaption "
            "machinery used or referenced by this repository. The Jamshidian engine docs "
            "explicitly point to Caspers' note on start-delay handling, while the "
            "short-rate calibration workflow is closely aligned with Caspers' QuantLib "
            "implementation papers on Gaussian and Markov-functional models."
        ),
        "papers": [
            {
                "title": "Jamshidian Swaption Formula Fine Tuned",
                "authors": "Peter Caspers",
                "year": 2013,
                "url": "https://ssrn.com/abstract=2246054",
                "notes": (
                    "Explicitly referenced by QuantLib's Jamshidian swaption engine for "
                    "start-delay treatment."
                ),
            },
            {
                "title": "One Factor Gaussian Short Rate Model Implementation",
                "authors": "Peter Caspers",
                "year": 2013,
                "url": "https://www.econbiz.de/10013083737",
                "notes": (
                    "Directly relevant to the repo's one-factor short-rate swaption "
                    "calibration workflow in QuantLib."
                ),
            },
            {
                "title": "Markov Functional One Factor Interest Rate Model Implementation in QuantLib",
                "authors": "Peter Caspers",
                "year": 2013,
                "url": "https://www.deriscope.com/docs/Markov_Functional_Peter_Caspers_2013.pdf",
                "notes": (
                    "QuantLib-focused paper for the Gaussian and Markov-functional "
                    "framework used by the broader swaption engine family."
                ),
            },
        ],
    },
    {
        "title": "Foundational European And Bermudan Swaption Papers",
        "intro": (
            "These are the papers most relevant to the pricing methods surfaced in the "
            "workstation: one-factor decomposition for European swaptions, and dynamic "
            "exercise methods for Bermudan swaptions."
        ),
        "papers": [
            {
                "title": "An Exact Bond Option Formula",
                "authors": "Farshid Jamshidian",
                "year": 1989,
                "url": "https://doi.org/10.1111/j.1540-6261.1989.tb02413.x",
                "notes": (
                    "Foundational decomposition result underlying Jamshidian-style "
                    "European swaption valuation in one-factor affine short-rate models."
                ),
            },
            {
                "title": "A Simple Approach to the Pricing of Bermudan Swaptions in the Multi-Factor LIBOR Market Model",
                "authors": "Leif B. G. Andersen",
                "year": 1999,
                "url": "https://ssrn.com/abstract=155208",
                "notes": (
                    "Classic early-exercise Monte Carlo boundary method for Bermudan "
                    "swaptions under a multifactor LIBOR market model."
                ),
            },
            {
                "title": "Throwing Away a Billion Dollars: The Cost of Suboptimal Exercise Strategies in the Swaptions Market",
                "authors": "Francis A. Longstaff, Pedro Santa-Clara, Eduardo S. Schwartz",
                "year": 2001,
                "url": "https://doi.org/10.1016/S0304-405X(01)00073-3",
                "notes": (
                    "Seminal paper on the economic importance of correct Bermudan swaption "
                    "exercise policy."
                ),
            },
        ],
    },
]


CLIQUET_RESEARCH_SECTION = {
    "title": "Equity Cliquet Papers",
    "intro": (
        "These ten references cover pricing, hedging, approximation, stochastic "
        "volatility, Levy and jump models, and retail-structured variants of equity "
        "cliquet-style products."
    ),
    "papers": [
        {
            "title": "Numerical Methods and Volatility Models for Valuing Cliquet Options",
            "authors": "Heather A. Windcliff, Peter A. Forsyth, and Kenneth R. Vetzal",
            "year": 2006,
            "url": "https://www.tandfonline.com/doi/full/10.1080/13504860600839964",
            "notes": "Benchmark numerical methods paper for cliquet valuation under alternative volatility models.",
        },
        {
            "title": "Locally-Capped Investment Products and the Retail Investor",
            "authors": "Carole Bernard, Phelim P. Boyle, and William Gornall",
            "year": 2011,
            "url": "https://researchportal.vub.be/en/publications/locally-capped-investment-products-and-the-retail-investor/",
            "notes": "Direct study of locally capped cliquet-style retail structures.",
        },
        {
            "title": "Pricing and Hedging of Cliquet Options and Locally-Capped Contracts",
            "authors": "Carole Bernard and Wei Li",
            "year": 2013,
            "url": "https://researchportal.vub.be/en/publications/pricing-and-hedging-of-cliquet-options-and-locally-capped-contrac/",
            "notes": "Core reference for integral representations and hedging of capped local-return structures.",
        },
        {
            "title": "Numerical Experiments on Hedging Cliquet Options",
            "authors": "Fiodar Kilin, Morten Nalholm, and Uwe Wystup",
            "year": 2014,
            "url": "https://researchprofiles.ku.dk/da/publications/numerical-experiments-on-hedging-cliquet-options/",
            "notes": "Peer-reviewed hedging study focused specifically on cliquet options.",
        },
        {
            "title": "Efficient Valuation of Equity-Indexed Annuities Under Levy Processes Using Fourier-Cosine Series",
            "authors": "Geng Deng, Tim Dulaney, Craig McCann, and Mike Yan",
            "year": 2017,
            "url": "https://www.risk.net/journal-of-computational-finance/5316511/efficient-valuation-of-equity-indexed-annuities-under-levy-processes-using-fourier-cosine-series",
            "notes": "Monthly point-to-point EIA credits are treated as cliquet payoffs and valued with COS methods.",
        },
        {
            "title": "Applications of the Central Limit Theorem for Pricing Cliquet-Style Options",
            "authors": "Ralf Korn, Busra Zeynep Temocin, and Jorg Wenzel",
            "year": 2017,
            "url": "https://publica.fraunhofer.de/entities/publication/b0fc0ae7-213e-4bfc-bb8e-1320a298cb21",
            "notes": "Analytical approximation and control-variate Monte Carlo for cliquet-style payoffs.",
        },
        {
            "title": "Equity-Linked Annuity Pricing with Cliquet-Style Guarantees in Regime-Switching and Stochastic Volatility Models with Jumps",
            "authors": "Zhenyu Cui",
            "year": 2017,
            "url": "https://doi.org/10.1016/j.insmatheco.2017.02.010",
            "notes": "Transform-based pricing of cliquet-style guarantees under richer stochastic-volatility and jump models.",
        },
        {
            "title": "Cliquet Option Pricing with Meixner Processes",
            "authors": "Markus Hess",
            "year": 2018,
            "url": "https://www.vmsta.org/journal/VMSTA/article/107",
            "notes": "Closed-form and transform methods for cliquets under a Meixner Levy process.",
        },
        {
            "title": "Cliquet Option Pricing in a Jump-Diffusion Levy Model",
            "authors": "Markus Hess",
            "year": 2018,
            "url": "https://www.vmsta.org/journal/VMSTA/article/118/read",
            "notes": "Jump-diffusion Levy pricing formulas plus Greeks with emphasis on vega.",
        },
        {
            "title": "CVA for Cliquet Options Under Heston Model",
            "authors": "Yaqin Feng, Min Wang, and Yuanqing Zhang",
            "year": 2019,
            "url": "https://doi.org/10.1016/j.najef.2019.02.008",
            "notes": "Extends cliquet valuation into counterparty-risk and Heston-model exposure analytics.",
        },
    ],
}
