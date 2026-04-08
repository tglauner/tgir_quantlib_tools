# LaTeX Documentation

This directory contains the audience-specific LaTeX documentation set for `tgir_quantlib_tools`.

## Documents
- `end_user_guide.tex` and `end_user_slides.tex`
- `quant_guide.tex` and `quant_slides.tex`
- `developer_guide.tex` and `developer_slides.tex`
- `it_operations_guide.tex` and `it_operations_slides.tex`
- `testing_regression_guide.tex`
- `deployment_cicd_digitalocean_guide.tex`

## Build

Build every PDF:

```bash
make -C docs/latex
```

Build one PDF:

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error docs/latex/end_user_guide.tex
```

Clean generated files:

```bash
make -C docs/latex clean
```
