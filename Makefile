.PHONY: install test run demo

install:
	pip install -r requirements.txt && pip install -e .

test:
	pytest -q

# Dados REAIS (API do Banco Central; precisa de internet)
run:
	python -m creditmonitor.pipeline --source live

# Demonstração offline com dados SINTÉTICOS (não são dados do BCB)
demo:
	python -m creditmonitor.pipeline --source synthetic
