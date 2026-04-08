LATEXMK=latexmk
LATEXFLAGS=-pdf -interaction=nonstopmode -halt-on-error

ARTICLE_DOCS=\
	end_user_guide.pdf \
	quant_guide.pdf \
	developer_guide.pdf \
	it_operations_guide.pdf \
	testing_regression_guide.pdf \
	deployment_cicd_digitalocean_guide.pdf

SLIDE_DOCS=\
	end_user_slides.pdf \
	quant_slides.pdf \
	developer_slides.pdf \
	it_operations_slides.pdf

ALL_DOCS=$(ARTICLE_DOCS) $(SLIDE_DOCS)

.PHONY: all clean

all: $(ALL_DOCS)

%.pdf: %.tex
	$(LATEXMK) $(LATEXFLAGS) $<

clean:
	$(LATEXMK) -C
