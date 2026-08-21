.PHONY: install run test lint compile

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
