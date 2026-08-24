.PHONY: install run test lint compile knowledge-init knowledge-rebuild knowledge-status

install:
	python -m pip install -e ".[dev]"

run:
	uvicorn app.main:app --host 0.0.0.0 --port 8000

test:
	pytest

lint:
	ruff check .

compile:
	python -m compileall app

knowledge-init:
	python -m app.knowledge.cli init

knowledge-rebuild:
	python -m app.knowledge.cli rebuild

knowledge-status:
	python -m app.knowledge.cli status
