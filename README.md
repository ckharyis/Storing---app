# Secure Lending Application Portal

A Django-based, mobile-friendly loan-request and electronic-signature portal designed for GitHub and Render. The repository ships in **demonstration mode** and accepts fictional data only until the production compliance gate is completed.

## What is included

- Public application form with explicit terms and privacy consent.
- Manual application review with controlled status changes.
- Invite-only staff accounts with mandatory authenticator-app MFA and one-use recovery codes.
- Owner/reviewer roles; only owners can create or send agreements.
- Dutch agreement generator derived from the supplied `Overeenkomst onderhandse lening` document.
- Clear principal, interest, total repayment, APR, term, late fee and installment schedule.
- Secure signing links stored as hashes, ten-minute email OTPs and touch/mouse signature capture.
- Draft and final PDFs, document hashes, consent evidence and audit events.
- Login and submission throttling, CSRF protection, strict cookies, CSP/HSTS configuration and private-file delivery through authorized views.
- PostgreSQL, private S3-compatible storage and SMTP configuration for production.
- Render Blueprint, Dockerfile, tests and deployment checks.

## Critical legal and privacy gate

The supplied agreement was used only as a structural reference. Its sample person's name, ID number and existing signature are **not included** in this repository. The source also contained conflicting principal/repayment wording, no clear interest calculation, no APR, no installment amounts and clauses that need Curaçao legal review.

The code therefore does all of the following:

1. Defaults to `DEMO_MODE=true`.
2. Shows a visible demonstration warning.
3. Requires fictional demo data confirmation.
4. Marks generated demo agreements as not for real use.
5. Requires the lender's legal identity, address, registration number and authorization reference before production can start.
6. Blocks production startup unless private object storage, email security, CAPTCHA and an explicit compliance acknowledgement are configured.

Do not change `PRODUCTION_COMPLIANCE_ACK` to `CONFIRMED` until Curaçao counsel and the relevant regulator have confirmed the company's authority, pricing/APR method, privacy notice, retention period and final agreement wording. A public-facing brand may differ from the registered company name, but the operating legal entity must still be disclosed in the footer, terms and agreement.

## Local setup

Requirements: Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py runserver
```

Django does not automatically read `.env`. Export the variables in your shell or use your preferred local environment loader. The defaults are safe for local demo use.

## Create the first staff owner

No web-based staff registration exists. Create staff from a trusted shell:

```bash
export INITIAL_ADMIN_PASSWORD='use-a-long-unique-password'
python manage.py create_staff --username owner --email owner@example.com --role owner
unset INITIAL_ADMIN_PASSWORD
```

At first login, the owner must scan the authenticator QR code and store the one-use recovery codes offline. Create reviewers with `--role reviewer`. Reviewers may handle requests; owners create and send agreements.

## Tests and checks

```bash
python manage.py test
python manage.py check
python manage.py makemigrations --check --dry-run
```

Before accepting real applications:

```bash
python manage.py production_check
```

This command intentionally fails in demo mode.

## Zero-cost Render demo

The included `render.yaml` uses Render's free web-service and PostgreSQL plans. It is suitable only for fictional demonstrations:

- The web service spins down after inactivity and can take about a minute to wake up.
- The free PostgreSQL database expires after 30 days and has no backups.
- The free web service has no Shell access and blocks ordinary SMTP ports.
- Generated agreements and signatures stored on the local filesystem can disappear after a restart or redeploy.

Deploy it as follows:

1. Put this folder in a **private** GitHub repository.
2. In Render, create a Blueprint from `render.yaml`; the estimate should show `$0/month`.
3. Keep `DEMO_MODE=true` and use only fictional information.
4. Set `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and `SITE_BASE_URL` to the Render HTTPS domain.
5. Enter safe fictional lender details for every business field.
6. Enter `INITIAL_ADMIN_USERNAME`, `INITIAL_ADMIN_EMAIL` and a unique password of at least 16 characters in `INITIAL_ADMIN_PASSWORD`.
7. Deploy the Blueprint. The first build creates the owner only when no owner already exists.
8. After the first successful deploy, delete `INITIAL_ADMIN_PASSWORD` from the web service's Render environment settings. Future builds skip bootstrapping because an owner already exists.
9. Log in at `/staff/login/`, enroll authenticator-app MFA and save the recovery codes offline.

The Blueprint intentionally deploys in demo mode and never contains a real company identity or secret.

## Upgrade before production

Do not accept real loan requests on free infrastructure. Before production, upgrade to durable services and then:

1. Configure the approved public brand and every required legal-identity value.
2. Configure SMTP or an approved email provider with a verified sender domain.
3. Configure Turnstile.
4. Configure a private S3-compatible bucket. Do not store contracts or signatures on Render's local filesystem in production.
5. Complete legal/privacy/security review, then change `DEMO_MODE=false` and set `PRODUCTION_COMPLIANCE_ACK=CONFIRMED`.
6. Run `python manage.py production_check` and test backup restoration before accepting real applications.

## Production environment variables

See `.env.example`. Production requires at minimum:

- A unique `SECRET_KEY`, `MFA_ENCRYPTION_KEY` and `IP_HASH_KEY`.
- PostgreSQL `DATABASE_URL` with TLS.
- The approved brand and complete legal lender identity.
- CBCS licence/dispensation/exemption reference or the exact approved disclosure.
- SMTP credentials and a verified `DEFAULT_FROM_EMAIL`.
- Turnstile site and secret keys.
- Private S3-compatible storage credentials and bucket.
- `PRODUCTION_COMPLIANCE_ACK=CONFIRMED` after review.

Store these in Render environment settings, never in GitHub.

## Electronic-signature evidence

The signing workflow records:

- The exact draft PDF hash.
- Agreement and consent versions.
- Verified applicant email and one-time-code event.
- Typed legal name and drawn signature image.
- Curaçao timestamp plus keyed hashes of the IP and user agent.
- Final signed-PDF hash and an internal audit reference.

This provides a useful evidence trail but is not a certified identity service. If counsel requires stronger identity assurance or a qualified certificate provider, replace the built-in signing step with an approved electronic-signature provider.

## Data-handling rules

- Never commit `.env`, SQLite files, `protected_media`, generated PDFs, IDs, salary slips or database exports.
- Never email ID documents or salary slips as ordinary attachments.
- Do not log raw passwords, OTPs, tokens, IDs, applications or agreements.
- Keep staff accounts individual and MFA-protected.
- Review and delete data when its configured retention period ends, subject to legal recordkeeping duties.
- Use test records only outside production.

## Planned full-application expansion

The next phase can add date/place of birth, address, ID and salary-slip uploads, employment/income information, save-and-resume links and a customer status page. Those fields should only be enabled after data minimization, lawful purpose, retention and private-upload rules are approved.
