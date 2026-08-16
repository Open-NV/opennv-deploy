# Security policy

## Supported versions

Security fixes are applied to the latest release on the default branch.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub's private
security advisory workflow for the OpenNV Deploy repository and include the
affected revision, deployment topology, reproduction steps, and impact. The
maintainers will acknowledge a complete report within five business days.

## Deployment invariants

- The public demo must not contain the Nornir executor or real-device secrets.
- MongoDB and CliSynth remain private Railway services.
- Generated build contexts and environment files never enter Git history.
- Content reload endpoints remain disabled unless a dedicated secret of at
  least 32 characters is provisioned through the deployment platform.
- A successful build is not release evidence; health, API, emulated execution,
  persistence, and browser behavior must all be verified.
