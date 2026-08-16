# OpenNV Deploy

Reproducible deployment packaging and smoke tests for the independently
versioned OpenNV projects.

## Local integrated stack

Clone the public repositories as siblings, copy `.env.example` to `.env`, set
three distinct local tokens, and run:

```bash
cp .env.example .env
# Replace each token placeholder with a different value from: openssl rand -hex 32
docker compose up --build -d
python3 tests/smoke.py \
  --base-url http://localhost:8080 \
  --console-url http://localhost:4173 \
  --clisynth-url http://localhost:8090
docker compose down
```

The local stack contains MongoDB, CliSynth, the OpenNV API and console, plus the
Nornir executor for an explicitly configured lab. Services bind to
`127.0.0.1`; the Mongo volume is retained by default. Run
`docker compose down --volumes` only when intentionally deleting local data.

## Public Railway demo

The Railway topology is smaller and safer: managed MongoDB, private CliSynth,
and one public image containing the API and console. It does not deploy the
executor, accept device credentials, or enable pack reload endpoints.

Because each OpenNV project has its own repository, run:

```bash
python3 scripts/build_railway_contexts.py
```

The assembler creates ignored build contexts under `.generated/railway` and a
content-addressed manifest of the exact source inputs. See
[`railway/README.md`](railway/README.md) for the complete CLI deployment and
terminal verification flow.

## Validation

```bash
make check
```

`tests/validate.py` checks the Compose wiring, generates both Railway contexts,
and verifies pack paths, same-origin `VITE_API_URL`, health configuration, and
the absence of an executor in the public app image.

## Security boundary

- Real execution accepts only a `credentialRef`; requests and result records do
  not contain credential values.
- Local executor access uses a dedicated bearer token and a distinct device
  network. Production requires a vault-backed resolver and enforced egress.
- The public demo sets `OPENNV_DEMO_MODE=true`, leaves all real-execution
  variables unset, and uses only private Railway networking for MongoDB and
  CliSynth.
- Generated contexts reject symlinks and omit `.git`, dependencies, test
  artifacts, caches, and local environment files.

Kubernetes packaging is deferred until the API and content contracts stabilize.
