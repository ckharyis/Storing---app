# Security policy

Do not report vulnerabilities through the public loan form. Use the private security contact configured by the operator.

## Mandatory operating rules

- Never commit `.env`, database exports, IDs, salary slips, signatures, generated agreements or API credentials.
- Keep the GitHub repository private and enable dependency alerts and secret scanning.
- Require MFA for every staff account; do not share accounts.
- Use paid PostgreSQL and private S3-compatible storage in production.
- Keep `DEMO_MODE=true` until legal identity, authorization, privacy, email, object storage and contract wording have been reviewed.
- Rotate a credential immediately if it appears in Git history.
- Review audit logs and failed-login patterns regularly without logging raw IDs, passwords, OTPs, tokens or contract contents.
- Test backup restoration before accepting real applications.

## Reporting scope

Include a concise description, affected endpoint, reproduction steps and impact. Do not access, copy or modify another person's data while testing.
