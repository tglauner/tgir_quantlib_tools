LATEXMK ?= latexmk

.PHONY: all summary clean count

all: tgir_quantlib_tools_chronology.pdf tgir_quantlib_tools_summary_20.pdf

tgir_quantlib_tools_chronology.pdf: lecture.tex sections/*.tex
	$(LATEXMK) -pdf -interaction=nonstopmode -halt-on-error -jobname=tgir_quantlib_tools_chronology lecture.tex

tgir_quantlib_tools_summary_20.pdf: summary_20.tex assets/*.jpg
	$(LATEXMK) -pdf -interaction=nonstopmode -halt-on-error -jobname=tgir_quantlib_tools_summary_20 summary_20.tex

summary: tgir_quantlib_tools_summary_20.pdf

count: tgir_quantlib_tools_chronology.pdf tgir_quantlib_tools_summary_20.pdf
	pdfinfo tgir_quantlib_tools_chronology.pdf | awk '/^Pages:/ {print $$2}'
	pdfinfo tgir_quantlib_tools_summary_20.pdf | awk '/^Pages:/ {print $$2}'

clean:
	$(LATEXMK) -C -jobname=tgir_quantlib_tools_chronology lecture.tex
	$(LATEXMK) -C -jobname=tgir_quantlib_tools_summary_20 summary_20.tex
