# LaTeX Documentation

This directory contains the LaTeX sources for the `tgir_quantlib_tools` documentation set. Final PDFs are written directly to `docs/`; all LaTeX intermediate files stay in the ignored `docs/latex/build/` directory.

Layout
- `documents/`: article-style `.tex` sources and their supporting files.
- `slides/`: Beamer `.tex` slide decks.
- `shared/`: canonical shared styles (`template_tgir_article.sty` and `template_tgir_beamer.sty`), preambles, and assets.

Every ordinary article source must use `\documentclass[conference]{IEEEtran}` and load `shared/tgir-article-preamble.tex`. `sample_article.pdf` is the canonical article-format reference. Article sources must use `\TGIRArticleAuthorBlock` and may not redefine fonts, geometry, title or section formatting, paragraph/list spacing, headers, footers, hyperlink colors, or page numbering. Wide content must wrap within a column or use an IEEE `table*`/`figure*`; it must not change the shared typography to fit.

Every ordinary slide source must load the TGIR Beamer template, directly or through `shared/tgir-beamer-preamble.tex`. Do not import the archived `mastering_ir_derivatives_*` styles for new or maintained documents. Status logic is the sole exception: its generated files and PDF remain self-contained under `status/`.

All article and Beamer entrypoints use the shared TGIR templates and preambles in `shared/`.

## Build

Build every PDF:

```bash
make -C docs/latex
```

Build one PDF (example):

```bash
make -C docs/latex ../sample_article.pdf
```

Clean generated files:

```bash
make -C docs/latex clean
```

The `Makefile` discovers sources in `documents/` and `slides/`. Before building, `check-article-style` rejects article sources that bypass or override the canonical article format.
