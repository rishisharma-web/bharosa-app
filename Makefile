# On Windows without make, use: python tasks.py <seed|run|test|snapshot>
PY ?= python
seed:     ; $(PY) tasks.py seed
run:      ; $(PY) tasks.py run
test:     ; $(PY) tasks.py test
snapshot: ; $(PY) tasks.py snapshot
smoke:    ; $(PY) tasks.py smoke
.PHONY: seed run test snapshot smoke
