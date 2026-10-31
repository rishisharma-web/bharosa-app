# On Windows without make, use: python tasks.py <seed|run|test|smoke|pdf>
PY ?= python
seed:  ; $(PY) tasks.py seed
run:   ; $(PY) tasks.py run
test:  ; $(PY) tasks.py test
smoke: ; $(PY) tasks.py smoke
pdf:   ; $(PY) tasks.py pdf
.PHONY: seed run test smoke pdf
