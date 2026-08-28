# Contributing to Ledger

Thank you for your interest in contributing! Ledger is currently a personal project, but we welcome feedback, bug reports, and contributions.

---

## Getting Started

### Set Up Your Development Environment

1. **Fork the repository** (if you plan to submit a PR)
2. **Clone locally**:
   ```bash
   git clone https://github.com/you/ledger.git
   cd ledger
   ```

3. **Follow the setup in README.md**:
   - `cd backend && cp .env.example .env` and fill in Plaid sandbox credentials + `ENCRYPTION_KEY`
   - Create a branch: `git checkout -b feature/your-feature-name`

---

## Development Guidelines

### Code Style

**Python**:
- Follow [PEP 8](https://pep8.org/)
- Use type hints for all functions
- Format with `black` (configured in `pyproject.toml`)
- Max line length: 100 characters

**TypeScript/React**:
- Use ESLint configuration (already in the project)
- Functional components with hooks (no class components)
- Props should be typed with interfaces
- Max line length: 100 characters

### Commits & Pull Requests

**Commit Messages**:
- Use clear, descriptive messages in imperative mood
- Examples: "Add budget alerting", "Fix transaction sync cursor bug", "Refactor categorization engine"
- Reference issue numbers if applicable: "Fixes #42"

**Pull Requests**:
- One feature per PR when possible
- Include a description of what changed and why
- Reference related issues
- Ensure all tests pass before requesting review

### Testing

**Backend**:
- Write tests for new features in `backend/tests/`
- Use `pytest` for unit and integration tests
- Run: `cd backend && pytest tests/`

**Frontend** (Vitest is configured; test files not yet added):
- Run: `cd frontend && npm run test`

**Manual Testing**:
- Test the feature end-to-end in the browser
- Test with Plaid Sandbox credentials
- Verify existing features still work (no regressions)

### Branches & Releases

- **main**: production-ready code. All merges via PR with code review.
- **feature/xxx**: new features (branch off `main`)
- **fix/xxx**: bug fixes (branch off `main`)
- No force pushes to `main`; rebase locally before pushing

### Documentation

- Update **README.md** if you add a major feature or change setup instructions
- Update **CLAUDE.md** if you add important architecture patterns or common tasks
- Update **docs/ARCHITECTURE.md** if you change data flow or core design
- Write docstrings for complex functions (but avoid over-commenting obvious code)

### Security

- **Never commit secrets**: API keys, passwords, encryption keys, or real credentials
- Use `.env.example` to document required env vars
- Ensure `.env` is in `.gitignore`
- Review **SECURITY.md** before adding new features that handle sensitive data
- If you discover a security issue, email a report privately instead of opening an issue

---

## Build & Release Process

### Before Submitting a PR

1. **Run tests**:
   ```bash
   cd backend && pytest tests/
   cd ../frontend && npm run lint && npm run build
   ```

2. **Lint & format (backend)**:
   ```bash
   cd backend && black . && flake8 .
   ```

3. **Lint (frontend)**:
   ```bash
   cd frontend && npm run lint
   ```

4. **Test locally**: single-port: `npm run build` (frontend) + `uvicorn` (backend)

### Release Checklist (Maintainers)

1. Ensure all tests pass
2. Update version in `package.json` and `pyproject.toml` if applicable
3. Note changes in **CHANGES.md**
4. Create a git tag and GitHub Release if shipping a milestone

---

## Architecture & Design

Before making significant changes, review:
- **CLAUDE.md**: development setup, key decisions, code patterns
- **docs/ARCHITECTURE.md**: data flow and component overview
- **Interactive API docs**: `http://localhost:8000/docs` when the backend is running

### If You Want to Add a Major Feature

1. **Check README.md** for how the feature fits the current scope
2. **Open an issue** describing the feature and how it fits into the architecture
3. **Wait for feedback** before investing time in implementation
4. **Design small**: Limit scope to a single concern (e.g., "Add budget alerts" not "refactor all dashboards")

---

## Common Issues & FAQs

### "My Plaid Link isn't working"
- Ensure you have `PLAID_ENV=sandbox` and valid sandbox credentials in `.env`
- Check the browser console for errors in the Plaid Link component
- Verify `POST /api/plaid/create_link_token` returns a valid token (see `/docs`)

### "Transactions aren't syncing"
- Check that a sync job ran: `POST /api/plaid/sync` (with `Authorization: Bearer <token>` or optional `X-API-Key`)
- Check backend logs for errors in `sync_engine.py`
- Verify the access token is encrypted in the database (`items` table)

### "Tests are failing"
- Ensure you're using Python 3.11+ and Node.js 18+
- Clear caches: `rm -rf backend/__pycache__ frontend/node_modules`
- Re-install dependencies: `pip install -r requirements.txt && npm install`

### "How do I run a single test?"
```bash
cd backend
pytest tests/test_auth.py -v
```

---

## Reporting Issues

### Bug Reports
Include:
- Steps to reproduce
- Expected vs. actual behavior
- Your environment (Python version, browser, OS)
- Relevant log output (without exposing secrets)

### Feature Requests
Include:
- What problem does this solve?
- How would it fit into the project scope?
- Any technical concerns or complexity?

---

## Questions?

- Read **CLAUDE.md** for developer guidance
- Check **docs/ARCHITECTURE.md** for design decisions
- Review **docs/PLAID_SETUP.md** for Plaid-specific questions
- See **SECURITY.md** for security and data handling questions

---

## Code of Conduct

Be respectful, inclusive, and professional. We're all here to build something cool!

---

**Thank you for contributing!** Every fix, test, and documentation improvement helps make Ledger better.
