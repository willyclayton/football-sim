# All-22 Play Viewer. Run from the repo root.
#
#   make bundle     download (if needed), validate, pack and copy plays into the app
#   make review     list plays awaiting video review
#   make review PLAY=2017090700-160 VERDICT=reviewed NOTE="matches broadcast"
#   make test       pipeline tests
#
# Uses a local virtualenv in .venv. To use another Python instead:  make bundle PY=python3

PYTHON  ?= python3
VENV    := .venv
DEFAULT_PY := $(CURDIR)/$(VENV)/bin/python
PY      ?= $(DEFAULT_PY)
EDITION ?= bdb2019-sample

ifeq ($(PY),$(DEFAULT_PY))
DEPS := $(VENV)/.installed
endif

RUN = cd pipeline && $(PY) -m all22

.PHONY: setup download bundle build review test fixtures clean

$(VENV)/.installed: pipeline/requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/python -m pip install -q --upgrade pip
	$(VENV)/bin/python -m pip install -q -r pipeline/requirements.txt
	touch $@

setup: $(DEPS)

download: $(DEPS)
	$(RUN) download --edition $(EDITION)

bundle: $(DEPS)
	$(RUN) bundle --edition $(EDITION)

build: $(DEPS)
	$(RUN) build --edition $(EDITION)

review: $(DEPS)
ifdef PLAY
	$(RUN) review $(PLAY) $(VERDICT) "$(NOTE)"
else
	$(RUN) review
endif

test: $(DEPS)
	cd pipeline && $(PY) -m pytest

fixtures: $(DEPS)
	$(RUN) fixtures

clean:
	rm -rf build
	find app/PlayData -mindepth 1 ! -name README.md -exec rm -rf {} +
