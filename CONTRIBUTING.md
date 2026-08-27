# Contributing

## Development workflow

1. Create a focused branch.
2. Implement and test one meaningful change.
3. Add an English bullet under the appropriate `CHANGELOG.md` `Unreleased`
   section in the same commit.
4. Run `ruff check .` and `pytest`.
5. Open a pull request that explains behavior, tests, and operational impact.

The changelog is part of the change, not a release-day afterthought. CI checks
that pull requests touching implementation or operational files also update
`CHANGELOG.md`.

## Commit style

Use concise imperative subjects, for example:

- `Add guarded revenue breakdown endpoint`
- `Fix invalid discount validation`
- `Document PostgreSQL backup procedure`
