# On Windows without make, use: python tasks.py <seed|run|test|smoke>
PY ?= python
seed:  ; $(PY) tasks.py seed
run:   ; $(PY) tasks.py run
test:  ; $(PY) tasks.py test
smoke: ; $(PY) tasks.py smoke
.PHONY: seed run test smoke
