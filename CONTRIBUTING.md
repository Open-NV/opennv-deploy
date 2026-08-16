# Contributing to OpenNV Deploy

Open an issue before changing trust boundaries or adding hosted services. Keep
each OpenNV project independently versioned; this repository may assemble
release contexts, but must not become a source-code monorepo.

Before submitting a pull request, run:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 tests/validate.py
ruff check scripts tests
```

Never commit `.env`, generated contexts, device credentials, Railway tokens, or
database URLs. Document any new public endpoint and add a terminal smoke check.
