# Security Policy

## Supported versions

Only the latest published release receives security fixes. PullPilot is distributed as a
container image from `ghcr.io/kn990x/pullpilot`; running `latest` (or the most recent
`MAJOR.MINOR` tag) is the supported configuration.

| Version | Supported |
|---------|-----------|
| Latest release | ✅ |
| Older releases | ❌ |

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately through GitHub:
[**Security → Report a vulnerability**](https://github.com/KN990x/PullPilot/security/advisories/new).

Please include:

- affected version or image tag,
- how the instance is exposed (LAN only, reverse proxy, public internet),
- reproduction steps and the impact you observed.

Expect an initial reply within 7 days. Fixes are shipped in a new release and documented
in a GitHub Security Advisory once users have had a chance to upgrade.

## Threat model and scope

PullPilot updates Docker Compose stacks, so **it requires access to the Docker socket and
to the stacks directory**. Anyone who can reach the UI can effectively run container
operations on the host. Treat it as an administrative tool.

In scope:

- authentication and session handling (`AUTH_USER` / `AUTH_PASS`, session cookie, login
  rate limiting),
- command injection or path traversal in project scanning and compose execution,
- leaking internal paths, command output, or secrets through the API or the UI,
- vulnerabilities in the shipped dependencies.

Out of scope:

- running with `ALLOW_NO_AUTH=true`, which disables authentication by design and is
  documented as "trusted networks only",
- exposing the UI to the internet without a reverse proxy, TLS, and credentials,
- the inherent privilege of the mounted Docker socket,
- vulnerabilities in the container images that PullPilot updates on your behalf.

## Hardening checklist

- Always set `AUTH_USER` and `AUTH_PASS`; leave `ALLOW_NO_AUTH` at `false`.
- Set a fixed `SESSION_SECRET` (`openssl rand -hex 32`). It is **mandatory** when
  `UVICORN_WORKERS > 1`.
- Behind HTTPS, set `SESSION_HTTPS_ONLY=true`; set `TRUST_X_FORWARDED_FOR=true` only when
  a trusted reverse proxy sits in front, so login rate limiting sees real client IPs.
- Restrict `CORS_ORIGINS` instead of leaving it empty (empty means "any origin").
- Do not publish the port to the internet directly; keep it on the LAN or behind a proxy.

## Automated security tooling

This repository runs CodeQL (default setup), Dependabot alerts and grouped security
updates, secret scanning with push protection, `pip-audit` for Python, and `npm audit`
for the frontend. See [`.github/workflows/`](.github/workflows/).
