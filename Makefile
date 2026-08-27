# Makefile — command surface per ENVIRONMENT_SETUP.md target table.
# Targets referencing later-phase scripts (validate/export/checkers/harness)
# are declared here and start working as those tasks land.

ENV ?= local
BRANCH ?= ui

.PHONY: setup new-iteration validate-iteration export web-tests api-tests lint \
	target-app-up target-app-seed target-app-reset target-app-healthcheck target-app-down

setup:
	uv sync
	uv run pre-commit install
	uv run playwright install chromium

new-iteration:
	uv run python scripts/new_iteration.py $(ID) --branch $(BRANCH)

validate-iteration:
	uv run python scripts/validate_schema.py iterations/$(ID)

export:
	uv run python scripts/export_xmind.py iterations/$(ID)
	uv run python scripts/export_xlsx.py iterations/$(ID)
	uv run python scripts/render_md.py iterations/$(ID)

web-tests:
	TEST_ENV=$(ENV) uv run pytest automation/web/tests/$(MODULE) --alluredir=reports/allure-results

api-tests:
	TEST_ENV=$(ENV) uv run pytest automation/api/tests/$(MODULE) --alluredir=reports/allure-results

lint:
	uv run ruff check .
	uv run pyright

target-app-up:
	uv run python scripts/target_app_up.py

target-app-seed:
	uv run python scripts/target_app_seed.py

target-app-reset:
	uv run python scripts/target_app_reset.py

target-app-healthcheck:
	uv run python scripts/target_app_healthcheck.py

target-app-down:
	uv run python scripts/target_app_down.py
