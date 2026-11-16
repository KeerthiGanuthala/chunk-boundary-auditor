.PHONY: install lint test fixtures audit experiments receipts docs verify evidence clean

PY ?= python

install:
	$(PY) -m pip install -e ".[dev]"

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

test:
	$(PY) -m pytest --junitxml=reports/junit.xml --cov=chunkaudit --cov-report=json:reports/coverage.json --cov-report=term-missing

# Regenerates the committed fixture from the packaged policy seed and fails if it drifted.
fixtures:
	$(PY) -m chunkaudit generate --check

# The one command that prints the headline table.
audit:
	$(PY) -m chunkaudit audit

experiments:
	$(PY) experiments/exp01_size_sweep.py
	$(PY) experiments/exp02_overlap_sweep.py
	$(PY) experiments/exp03_strategy_compare.py
	$(PY) experiments/exp04_extraction_loss.py

receipts:
	$(PY) tools/collect_metrics.py
	$(PY) tools/render_tables.py --check
	$(PY) tools/render_banner.py --check
	$(PY) tools/check_numbers.py

# Rewrites the README tables and the banner from the measured numbers.
docs:
	$(PY) tools/render_tables.py
	$(PY) tools/render_banner.py

verify: lint test fixtures experiments receipts

evidence:
	$(PY) tools/render_diagram.py
	$(PY) tools/capture_screenshots.py
	$(PY) tools/record_demo.py
	$(PY) tools/render_explainer.py

clean:
	rm -rf reports .pytest_cache .ruff_cache build dist *.egg-info src/*.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
