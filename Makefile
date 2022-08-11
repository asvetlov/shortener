setup:
	pip install -U pip poetry
	poetry install
	poetry run pre-commit install

lint:
	poetry run pre-commit run --all-files
	poetry run mypy . --strict --show-error-codes


build:
	poetry build
	docker-compose build

run: build
	docker-compose up


test:
	poetry run pytest tests

vtest:
	poetry run pytest -vvv tests
