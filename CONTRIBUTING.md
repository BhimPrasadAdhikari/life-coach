# Contributing to Coach Aria

Thanks for your interest in contributing to this project.

## Before You Start

1. Open an issue first for bugs, features, or refactors.
2. Wait for maintainers to confirm scope before implementing large changes.
3. Keep pull requests focused on one clearly defined change.

## Local Setup

1. Create and activate a Python virtual environment.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Copy env file:
   - `cp .env.example .env`
4. Add valid API keys in `.env`.

## Pull Request Process

1. Create a branch from `main`.
2. Implement only approved scope.
3. Run validation commands:
   - `bash build.sh`
   - `python -m pytest -q` (if tests are available in your environment)
4. Update docs if behavior/configuration changed.
5. Submit a PR with:
   - Clear title
   - Problem statement
   - Summary of changes
   - Validation proof (commands + result)

## Non-Negotiable Rules (Strict)

These rules are mandatory. Violations may lead to immediate PR rejection.

1. **Never commit secrets** (API keys, tokens, credentials, `.env`, database dumps).
2. **Do not add unapproved dependencies** without clear justification in the PR.
3. **Do not modify unrelated files** or include drive-by refactors.
4. **Do not break existing behavior**; preserve backward compatibility unless explicitly approved.
5. **Do not bypass validation**; run build/tests relevant to your change before opening PR.
6. **Do not push directly to `main`**; all changes must go through pull requests.
7. **Do not submit AI-generated code blindly**; review and verify correctness/security yourself.
8. **Do not weaken security/privacy** (unsafe input handling, data leakage, insecure defaults).
9. **Do not remove or alter license/authorship notices** unless maintainers request it.
10. **Be respectful and professional** in issues, reviews, and discussions.

## Quality Expectations

- Follow existing code style and architecture.
- Prefer small, readable, maintainable changes.
- Include rationale for non-trivial design choices.
- Keep documentation synchronized with code changes.

By contributing, you agree to follow this guide and all repository policies.
