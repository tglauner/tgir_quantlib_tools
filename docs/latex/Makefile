LATEXMK ?= latexmk
LATEX_ENGINE := -pdf
LATEXFLAGS := -interaction=nonstopmode -halt-on-error
BUILD_DIR := build
PAPER_DIR := ../papers

ARTICLE_DOCS := \
	callable_bermudan_xccy_quant_model_summary.pdf \
	deployment_cicd_digitalocean_guide.pdf \
	developer_guide.pdf \
	end_user_guide.pdf \
	exotic_derivatives_pricing_research.pdf \
	it_operations_guide.pdf \
	quant_guide.pdf \
	standalone_callable_xccy_pricer_spec.pdf \
	testing_regression_guide.pdf \
	xccy_callable_validation_report.pdf

SLIDE_DOCS := \
	end_user_slides.pdf \
	quant_slides.pdf \
	developer_slides.pdf \
	it_operations_slides.pdf

ALL_DOCS := $(ARTICLE_DOCS) $(SLIDE_DOCS)
ALL_SOURCES := $(ALL_DOCS:.pdf=.tex)
PAPER_TARGETS := $(addprefix $(PAPER_DIR)/,$(ALL_DOCS))

.PHONY: all clean

all: $(PAPER_TARGETS)

$(BUILD_DIR) $(PAPER_DIR):
	mkdir -p $@

$(PAPER_DIR)/callable_bermudan_xccy_quant_model_summary.pdf: LATEX_ENGINE := -xelatex

$(PAPER_TARGETS): $(PAPER_DIR)/%.pdf: %.tex | $(BUILD_DIR) $(PAPER_DIR)
	$(LATEXMK) $(LATEX_ENGINE) $(LATEXFLAGS) -outdir=$(BUILD_DIR) $<
	cp $(BUILD_DIR)/$(@F) $@

clean:
	$(LATEXMK) -C -outdir=$(BUILD_DIR) $(ALL_SOURCES)
	test ! -d $(BUILD_DIR) || find $(BUILD_DIR) -type f -delete
	test ! -d $(BUILD_DIR) || find $(BUILD_DIR) -depth -type d -empty -delete
