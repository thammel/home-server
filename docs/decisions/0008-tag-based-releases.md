# 0008. Releases are version tags on main, and the server runs a tag

- **Status:** accepted
- **Date:** 2026-11-18
- **Relates to:** `.github/workflows/release.yml`, `release-please-config.json`

## Context

Merging to `main` was the only release step: the server pulled the newest `main` and restarted. Nothing recorded which commit was running, what changed since the last deploy, or what to go back to after a bad update. A long-lived `develop` branch was considered to separate "merged" from "shipped".

## Decision

`main` stays the only long-lived branch; feature branches merge into it by PR. release-please keeps a release PR open that bumps the version in `pyproject.toml` and updates `CHANGELOG.md` from Conventional Commits. Merging that PR tags `vX.Y.Z` and publishes a GitHub Release. The server checks out a release tag, not the tip of `main`.

## Consequences

**Good:** every deploy is a named version with release notes. Rollback is checking out the previous tag. Merging a feature no longer ships it; merging the release PR decides when. Semver follows the commit types (`feat` minor, `fix` patch, `!` major) without manual bookkeeping.

**Bad:** release notes are only as good as the commit subjects; a wrong type puts a change in the wrong section or bumps the wrong number. Squash merges must keep a Conventional Commit title. One more PR per release. The workflow needs the repository setting that lets GitHub Actions create pull requests.

**Neutral:** `CHANGELOG.md` and the version in `pyproject.toml` are written by the bot, not by hand. Commits before the bootstrap commit are not in the changelog.

## Alternatives considered

| Option | Why not |
|---|---|
| `develop` branch, `main` = released | Second merge for every change; little gain with one maintainer |
| Tags pushed by hand | Easy to forget; no changelog |
| Keep deploying the tip of `main` | No record of what runs; no clean rollback |

## Revisit when

Several people merge in parallel and need a shared integration branch, or a release has to be built and tested as an artifact (e.g. a Docker image) before it is deployed.
