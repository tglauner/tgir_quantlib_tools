LATEXMK ?= latexmk
LATEXFLAGS := -pdf -interaction=nonstopmode -halt-on-error
BUILD_DIR := build

PDFS := \
	project_summary_20pages.pdf \
	quantlib_derivatives_lecture.pdf \
	supplementary_slides.pdf

.PHONY: all clean

all: $(PDFS)

$(PDFS): %.pdf: %.tex
	mkdir -p $(BUILD_DIR)
	$(LATEXMK) $(LATEXFLAGS) -outdir=$(BUILD_DIR) $<
	cp $(BUILD_DIR)/$@ $@

clean:
	$(LATEXMK) -C -outdir=$(BUILD_DIR) $(PDFS:.pdf=.tex)
	test ! -d $(BUILD_DIR) || find $(BUILD_DIR) -type f -delete
	test ! -d $(BUILD_DIR) || find $(BUILD_DIR) -depth -type d -empty -delete
