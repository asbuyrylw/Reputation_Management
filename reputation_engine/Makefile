# Reputation Engine -- dev tasks
# Usage: make <target>

.PHONY: install migrate test test-unit lint type db-test-up clean

install:
	pip install -r requirements.txt
	pip install pytest pytest-cov ruff mypy

# Build/update the database schema. Alembic is the single source of truth
# (alembic/versions/); this replaces the old hand-applied schema_v*.sql files.
migrate:
	alembic upgrade head

# Run only the no-DB unit tests (fast, no Postgres needed)
test-unit:
	pytest tests/test_unit_logic.py -q

# Run the full suite (needs REP_TEST_DSN pointing at a throwaway Postgres)
test:
	pytest -q

lint:
	ruff check rep_engine/

type:
	mypy rep_engine/ --ignore-missing-imports

clean:
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	rm -f output/*.docx
