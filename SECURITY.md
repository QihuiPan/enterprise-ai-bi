# Security

## Reporting

Do not open a public issue for a suspected vulnerability. Report it privately
to the repository owner with reproduction steps and impact.

## Implemented controls

- Natural-language questions never execute generated SQL.
- Agents can call only registered, read-only analytical tools.
- Uploads have a configurable size limit and a strict required schema.
- Revenue is derived by the server instead of trusted from uploaded files.
- Database credentials and frontend API URLs are supplied through environment
  variables and are not committed.
- API errors avoid returning stack traces to clients.

Before an internet-facing deployment, add authentication, per-tenant data
isolation, rate limiting, encrypted backups, centralized secrets management,
dependency scanning, and an allowlisted production CORS configuration.
