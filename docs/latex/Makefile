LATEXMK ?= latexmk
LATEX_ENGINE := -pdf
LATEXFLAGS := -interaction=nonstopmode -halt-on-error
BUILD_DIR := build
PDF_DIR := ..
SHARED_DIR := shared
SHARED_FILES := $(wildcard $(SHARED_DIR)/*)
TEXINPUTS := $(SHARED_DIR)//:

# Source layout
DOCS_DIR := documents
SLIDES_DIR := slides

DOC_TEX := $(wildcard $(DOCS_DIR)/*.tex)
SLIDE_TEX := $(wildcard $(SLIDES_DIR)/*.tex)
ALL_TEX := $(DOC_TEX) $(SLIDE_TEX)

DOC_PDF_TARGETS := $(addprefix $(PDF_DIR)/,$(notdir $(DOC_TEX:.tex=.pdf)))
SLIDE_PDF_TARGETS := $(addprefix $(PDF_DIR)/,$(notdir $(SLIDE_TEX:.tex=.pdf)))
PDF_TARGETS := $(DOC_PDF_TARGETS) $(SLIDE_PDF_TARGETS)

.PHONY: all check-article-style clean

all: check-article-style $(PDF_TARGETS)

check-article-style:
	@for src in $(DOC_TEX); do \
		rg -q -F '\documentclass[conference]{IEEEtran}' "$$src" || { echo "Missing IEEEtran conference class: $$src"; exit 1; }; \
		rg -q -F '\input{shared/tgir-article-preamble}' "$$src" || { echo "Missing canonical TGIR article preamble: $$src"; exit 1; }; \
		rg -q -F '\author{\TGIRArticleAuthorBlock}' "$$src" || { echo "Missing canonical TGIR author block: $$src"; exit 1; }; \
		rg -q -F '\maketitle' "$$src" || { echo "Missing canonical IEEE title rendering: $$src"; exit 1; }; \
	done
	@if rg -n '\\(usepackage\{(fontspec|lmodern|fancyhdr|titlesec|setspace|geometry)|setmainfont|setmonofont|pagestyle|thispagestyle|fancyhf|fancyhead|fancyfoot|lhead|rhead|lfoot|rfoot|cfoot|titleformat|titlespacing|setlist|setlength\{\\(parindent|parskip|textwidth|textheight|columnsep|oddsidemargin|evensidemargin|topmargin|headheight|footskip)|date\{|title\{\\(vspace|textbf|Large|large|normalsize))' $(DOC_TEX); then \
		echo "Article source overrides canonical template typography or layout."; exit 1; \
	fi

$(BUILD_DIR) $(PDF_DIR):
	mkdir -p $@

$(DOC_PDF_TARGETS): $(PDF_DIR)/%.pdf: $(DOCS_DIR)/%.tex $(SHARED_FILES) | $(BUILD_DIR) $(PDF_DIR)
	@TEXINPUTS="$(TEXINPUTS)" $(LATEXMK) $(LATEX_ENGINE) $(LATEXFLAGS) -outdir=$(BUILD_DIR) "$<" && \
	cp $(BUILD_DIR)/$(@F) $@

$(SLIDE_PDF_TARGETS): $(PDF_DIR)/%.pdf: $(SLIDES_DIR)/%.tex $(SHARED_FILES) | $(BUILD_DIR) $(PDF_DIR)
	@TEXINPUTS="$(TEXINPUTS)" $(LATEXMK) $(LATEX_ENGINE) $(LATEXFLAGS) -outdir=$(BUILD_DIR) "$<" && \
	cp $(BUILD_DIR)/$(@F) $@

clean:
	TEXINPUTS="$(TEXINPUTS)" $(LATEXMK) -C -outdir=$(BUILD_DIR) $(ALL_TEX)
	test ! -d $(BUILD_DIR) || find $(BUILD_DIR) -type f -delete
	test ! -d $(BUILD_DIR) || find $(BUILD_DIR) -depth -type d -empty -delete
