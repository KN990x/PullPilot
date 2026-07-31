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

- authentication and session handling (stored credentials hashed with scrypt, the setup
  wizard, session cookie and its signing secret, login rate limiting),
- command injection or path traversal in project scanning and compose execution,
- leaking internal paths, command output, or secrets through the API or the UI,
- vulnerabilities in the shipped dependencies.

Out of scope:

- exposing the UI to the internet without a reverse proxy, TLS, and credentials,
- the inherent privilege of the mounted Docker socket,
- vulnerabilities in the container images that PullPilot updates on your behalf.

There is no longer any way to disable authentication. The `ALLOW_NO_AUTH` escape hatch is
gone: with a setup wizard that takes ten seconds, an "open the whole API" switch was a
liability with no remaining purpose.

## The setup window

Between the very first start and completing the setup wizard, **anyone who can reach the
instance can claim it** by creating the administrator account. This is the same trade-off
Portainer and Home Assistant make, and it is deliberate: it is what makes the first run
zero-configuration. There is no time limit on the window.

Practical consequence: complete the wizard immediately after the first start, and do not
publish the port until you have. Once credentials exist, `/api/auth/setup` returns 409 and
the window is closed for good.

## Hardening checklist

The list is short on purpose: most of what used to be here was a knob you could set
wrongly, and each one is now either automatic or a fixed value.

- Complete the setup wizard right after the first start.
- The session signing secret is generated and persisted inside the data volume, at
  `session_secret.key` with mode `0600`. Anyone who can read that file can forge sessions,
  so keep the volume as private as the database itself.
- The session cookie is **signed, not encrypted** and lasts 30 days. Over plain HTTP it
  travels in the clear, and it is the only factor guarding something that controls the
  Docker socket.
- Behind a TLS-terminating reverse proxy, set `PUBLIC_URL=https://your.host`. That single
  value marks the cookie `Secure` and makes login rate limiting read `X-Forwarded-For`, so
  it sees real client IPs instead of the proxy's.
- `SameSite=lax` on the cookie, no CORS middleware at all, login rate limiting at 15
  attempts per 5 minutes: fixed, not configurable, so no deployment can weaken them.
- Do not publish the port to the internet directly; keep it on the LAN or behind a proxy.

## Automated security tooling

This repository runs Dependabot alerts and grouped security updates, secret scanning with
push protection, `pip-audit` for Python, and `pnpm audit` for the frontend. The audits run
weekly (and on demand) from [`security-audit.yml`](.github/workflows/security-audit.yml):
they are an alarm, not a merge gate, so they no longer decorate every pull request with a
check nobody can clear. The merge gate is [`ci.yml`](.github/workflows/ci.yml), which runs
lint, tests, the frontend build and a cold-start smoke test of the image.

The frontend additionally relies on two pnpm guarantees, configured in
[`web/pnpm-workspace.yaml`](web/pnpm-workspace.yaml): dependency install scripts are
blocked unless explicitly allowlisted, and a new resolution will not pick a version
published within the last 7 days.
