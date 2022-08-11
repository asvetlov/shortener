setup:
	pip install -U pip poetry
	poetry install
	python -m pre_commit install

lint:
	python -m pre_commit run --all-files
	python -m mypy . --strict --show-error-codes


build:
	poetry build
	docker-compose build

run: build
	docker-compose up


test:
	python -m pytest tests

vtest:
	python -m pytest -vvv tests
