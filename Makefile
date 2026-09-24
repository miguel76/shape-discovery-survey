# Shape discovery survey pipeline. Requirements: bash, git, Python >= 3.10,
# Java >= 17, Maven. See README.md.
KG ?= toy
TOOLS := $(shell python3 -c "import json;print(' '.join(json.load(open('tools/registry.json'))))")
TOOLS_HOME ?= $(CURDIR)/.tools
PY := $(TOOLS_HOME)/pipeline-venv/bin/python
export TOOLS_HOME

.PHONY: install install-pipeline run evaluate all

all: run evaluate

install: install-pipeline install-fuseki $(addprefix install-,$(TOOLS))

install-pipeline:
	[ -x $(PY) ] || python3 -m venv $(TOOLS_HOME)/pipeline-venv
	$(PY) -m pip install -q --disable-pip-version-check -r pipeline/requirements.txt

# (pattern rule, so these targets must not be .PHONY)
install-%: FORCE
	tools/$*/install.sh

# run all tools on data/$(KG) (file input, plus SPARQL-endpoint input where supported)
run:
	$(PY) pipeline/run.py $(KG) --endpoint

evaluate:
	$(PY) pipeline/evaluate.py $(KG)

FORCE:
