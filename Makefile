# Alternativa ao CMake. PY pode apontar para o Python do ambiente de construção.
ifeq ($(OS),Windows_NT)
PY ?= python
else
PY ?= python3
endif

CONFIG ?= exemplo_edf_2cpus.txt

.PHONY: all build test run completo

all: build

build:
	"$(PY)" construir.py

test:
	"$(PY)" -B -m unittest testes testes_regressao -v

run:
	"$(PY)" main.py "$(CONFIG)"

completo:
	"$(PY)" main.py "$(CONFIG)" --completo
