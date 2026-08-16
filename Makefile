.PHONY: contexts lint test validate check smoke

contexts:
	python3 scripts/build_railway_contexts.py

lint:
	ruff check scripts tests

test:
	python3 -m unittest discover -s tests -p 'test_*.py' -v

validate:
	python3 tests/validate.py

check: lint test validate

smoke:
	@test -n "$(OPENNV_URL)" || (echo "OPENNV_URL is required" >&2; exit 2)
	python3 tests/smoke.py --base-url "$(OPENNV_URL)" --validation-matrix
