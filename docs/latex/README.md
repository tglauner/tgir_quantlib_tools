# LaTeX Documentation

This directory contains the LaTeX sources for the `tgir_quantlib_tools` documentation set. Final PDFs are written to `docs/papers/`; all LaTeX intermediate files stay in the ignored `docs/latex/build/` directory.

## Documents

- `callable_bermudan_xccy_quant_model_summary.tex`
- `deployment_cicd_digitalocean_guide.tex`
- `developer_guide.tex` and `developer_slides.tex`
- `end_user_guide.tex` and `end_user_slides.tex`
- `exotic_derivatives_pricing_research.tex`
- `it_operations_guide.tex` and `it_operations_slides.tex`
- `quant_guide.tex` and `quant_slides.tex`
- `standalone_callable_xccy_pricer_spec.tex`
- `testing_regression_guide.tex`
- `xccy_callable_validation_report.tex`

## Build

Build every PDF:

```bash
make -C docs/latex
```

Build one PDF:

```bash
make -C docs/latex ../papers/end_user_guide.pdf
```

Clean generated files:

```bash
make -C docs/latex clean
```

The clean target removes intermediate files but retains final PDFs in `docs/papers/`.
The quantitative model summary uses XeLaTeX for its system fonts; the Makefile selects that engine automatically.
