# BuoyCast — Claude Code Instructions

## Workflow
- Commit after each task is complete (not at the end of a phase)
- Commit messages follow conventional commits: `feat:`, `fix:`, `chore:`, `test:`, etc.
- Run the full test suite before committing: `.venv/Scripts/python.exe -m pytest tests/ -v`

## Build/Run Commands
- Python tests: `.venv/Scripts/python.exe -m pytest tests/ -v`
- Dashboard build: `export PATH="/c/Program Files/nodejs:$PATH" && npm run build` (from dashboard/)
- Dashboard type-check: `npx tsc --noEmit` (from dashboard/)
- Install Python deps: `.venv/Scripts/python.exe -m pip install -e ".[dev]"`

## Conventions
- Pydantic v2 everywhere, no raw dicts between components
- Event bus with asyncio.Queue for inter-component communication
- pytest-asyncio with `asyncio_mode = "auto"`
- TypeScript: `erasableSyntaxOnly` is enabled — use `as const` objects instead of string enums
- shadcn/ui components go in `dashboard/src/components/ui/`

## Key Docs
- `docs/implementation-plan.md` — task breakdown and phase definitions
- `docs/architecture-plan.md` — system design and protocol details
- `docs/product-plan.md` — product requirements
