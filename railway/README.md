# Railway public emulation demo

The hosted demo deliberately contains no Nornir executor, device credentials,
or route to a production network. Its three-service topology is:

```text
browser -> opennv-app (public API + console)
                    |-> MongoDB (private managed service)
                    `-> clisynth (private service, 160 OutputFSM definitions)
```

The OpenNV projects remain independently versioned repositories. This deploy
repository assembles two ephemeral Docker build contexts from checked-out
sibling repositories and records every input file, size, SHA-256, Git revision,
and dirty flag in `BUILD-MANIFEST.json`. Generated contexts are ignored by Git.

## Prerequisites

- Railway CLI 5.23 or newer, authenticated to the target workspace;
- sibling checkouts named `opennv-validation`, `clisynth`,
  `outputfsm-packs`, and `validation-packs`;
- exactly 160 OutputFSM definitions and 160 validation definitions across the
  eight supported platforms.

Verify identity and assemble the contexts:

```bash
railway whoami --json
python3 scripts/build_railway_contexts.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## First deployment

Create the project in the intended workspace and add only the required
services. The Mongo service created by the CLI is named `MongoDB`.

```bash
railway init --name opennv-demo --workspace <workspace-id> --json
railway add --database mongo --json
railway add --service clisynth --json
railway add --service opennv-app --json
railway status --json
```

Wire the public application to private Railway DNS. Quotes are important so the
shell does not interpret Railway's reference syntax.

```bash
railway variable set \
  'OPENNV_DEMO_MODE=true' \
  'MONGODB_URI=${{MongoDB.MONGO_URL}}' \
  'MONGODB_DATABASE=opennv' \
  'CLISYNTH_URL=http://${{clisynth.RAILWAY_PRIVATE_DOMAIN}}:8080' \
  --service opennv-app --skip-deploys
```

Do not configure `NORNIR_EXECUTOR_URL`, `EXECUTOR_TOKEN`, inventory credentials,
or an executor service in this project. CliSynth's reload endpoint is disabled
because `CLISYNTH_RELOAD_TOKEN` is intentionally unset; content is immutable in
the public demo image.

Deploy the private renderer first, then the combined public API and console.
`--no-gitignore` is required because the generated contexts are intentionally
excluded from commits.

```bash
railway up .generated/railway/clisynth --path-as-root --no-gitignore \
  --service clisynth --ci -m "Deploy private CliSynth emulation service"
railway up .generated/railway/app --path-as-root --no-gitignore \
  --service opennv-app --ci -m "Deploy public OpenNV emulation demo"
railway domain --service opennv-app --port 8080 --json
```

The console is built with `VITE_API_URL=/v1` and is served by the API process,
so browser requests remain same-origin. `VITE_API_BASE_URL` is not a supported
setting.

## Verification

Read back state before calling the demo ready:

```bash
railway service list --json
railway deployment list --service clisynth --limit 3 --json
railway deployment list --service opennv-app --limit 3 --json
railway logs --service clisynth --lines 200 --json
railway logs --service opennv-app --lines 200 --json
python3 tests/smoke.py --base-url "https://<opennv-app-domain>" --validation-matrix
```

The smoke test proves the public console loads, the API reports demo mode, all
eight platforms expose exactly 20 commands, and one emulated command per
platform returns four persisted results from the `clisynth` backend (32 task
results total). The validation matrix then executes all 160 repository checks
against four synthetic devices per platform and verifies 640 persisted outcomes.
Baseline-independent checks must pass; baseline-dependent checks may be unknown
on a standalone run, while failed/error outcomes are rejected. The script does
not infer health merely from a successful upload or build. It also proves that
demo administration is forbidden, real execution has no configured backend,
and the console carries the expected CSP and MIME-sniffing protections.

## Subsequent deployment

Check out the intended revisions of each sibling repository, regenerate the
contexts, review `BUILD-MANIFEST.json`, and run the two targeted `railway up`
commands again. Once the public repositories exist, CI should check out exact
SHAs and invoke `python3 scripts/build_railway_contexts.py --require-clean`;
no cross-repository source is copied into Git history. The bootstrap deployment
may record dirty/uncommitted inputs explicitly, but release automation must fail
closed on them.
