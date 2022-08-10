setup:
	pip install -U pip
	poetry update
	pre-commit install

lint:
	pre-commit run --all-files
	mypy . --strict --show-error-codes
