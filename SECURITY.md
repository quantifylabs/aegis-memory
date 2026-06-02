# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 2.4.x   | ✅        |
| < 2.4   | ❌        |

## Reporting a Vulnerability

Aegis Memory is security-critical infrastructure — context is the attack surface, so we
take reports seriously.

**Please do not open public issues for security vulnerabilities.**

Report privately via either:
- GitHub's private vulnerability reporting: the **Security** tab → **Report a vulnerability**
- Email: **arulnidhi@quantifylabs.ai**

Include: affected version, reproduction steps, and impact assessment.

## Response Timeline

- Acknowledgement within **72 hours**
- Initial assessment within **7 days**
- Coordinated disclosure once a fix is available

For deeper security architecture (4-stage content pipeline, HMAC-SHA256 integrity,
OWASP 4-tier trust hierarchy), see [docs/guides/security.mdx](docs/guides/security.mdx).

## Dependency Vulnerabilities

The shipped-library dependency surface is audited against OSV in CI
([`.github/workflows/pip-audit.yml`](.github/workflows/pip-audit.yml)) and currently reports
**zero known vulnerabilities**. For the full triage — including the benchmark/dev-only residual
that is documented and accepted (never shipped to PyPI users) — see
[docs/security/vuln-triage.md](docs/security/vuln-triage.md).
