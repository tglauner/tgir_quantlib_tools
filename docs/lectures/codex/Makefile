LATEXMK ?= latexmk
LATEXFLAGS := -pdf -interaction=nonstopmode -halt-on-error
BUILD_DIR := build
SHARED_DIR := ../../latex/shared
SHARED_FILES := $(wildcard $(SHARED_DIR)/*)
# Preambles import styles as shared/<file>; expose the LaTeX root, not only
# the shared subdirectory, so the lecture builds from this directory too.
TEXINPUTS := ../../latex//:

.PHONY: all summary clean count

all: tgir_quantlib_tools_chronology.pdf tgir_quantlib_tools_summary_20.pdf

tgir_quantlib_tools_chronology.pdf: lecture.tex sections/*.tex $(SHARED_FILES)
	mkdir -p $(BUILD_DIR)
	TEXINPUTS="$(TEXINPUTS)" $(LATEXMK) $(LATEXFLAGS) -outdir=$(BUILD_DIR) -jobname=tgir_quantlib_tools_chronology lecture.tex
	cp $(BUILD_DIR)/$@ $@

tgir_quantlib_tools_summary_20.pdf: summary_20.tex assets/*.jpg $(SHARED_FILES)
	mkdir -p $(BUILD_DIR)
	TEXINPUTS="$(TEXINPUTS)" $(LATEXMK) $(LATEXFLAGS) -outdir=$(BUILD_DIR) -jobname=tgir_quantlib_tools_summary_20 summary_20.tex
	cp $(BUILD_DIR)/$@ $@

summary: tgir_quantlib_tools_summary_20.pdf

count: tgir_quantlib_tools_chronology.pdf tgir_quantlib_tools_summary_20.pdf
	pdfinfo tgir_quantlib_tools_chronology.pdf | awk '/^Pages:/ {print $$2}'
	pdfinfo tgir_quantlib_tools_summary_20.pdf | awk '/^Pages:/ {print $$2}'

clean:
	TEXINPUTS="$(TEXINPUTS)" $(LATEXMK) -C -outdir=$(BUILD_DIR) -jobname=tgir_quantlib_tools_chronology lecture.tex
	TEXINPUTS="$(TEXINPUTS)" $(LATEXMK) -C -outdir=$(BUILD_DIR) -jobname=tgir_quantlib_tools_summary_20 summary_20.tex
	test ! -d $(BUILD_DIR) || find $(BUILD_DIR) -type f -delete
	test ! -d $(BUILD_DIR) || find $(BUILD_DIR) -depth -type d -empty -delete
