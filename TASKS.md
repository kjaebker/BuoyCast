# TASKS.md — BuoyCast Work Tracker

All implementation phases complete. See [docs/TASKS-ARCHIVE.md](docs/TASKS-ARCHIVE.md) for full history.

---

## Completed Phases

| Phase | Description | Status |
|---|---|---|
| 1 | Foundation: Data Models, Config & Project Setup | ✅ |
| 2 | S4 Serial Protocol Layer | ✅ |
| 3 | TICKR Heart Rate Reader | ✅ |
| 4 | Storage Layer | ✅ |
| 5 | Workout State Machine & Recorder | ✅ |
| 6 | BLE FTMS Broadcaster | ✅ |
| 7 | REST API & WebSocket | ✅ |
| 8 | Strava Integration | ✅ |
| 9 | Dashboard | ✅ |
| 10 | Pi Setup, systemd & Install Script | ✅ |
| 11 | Hardening & Polish | ✅ |

---

## Future Work

Add new tasks here as they arise.

| ID | Task | Status | Updated |
|---|---|---|---|
| E1 | Backend: Database migration v3 + AppSettings model | done | 2026-03-15 |
| E2 | Backend: Settings API endpoints (GET/PUT /api/settings) | done | 2026-03-15 |
| E3 | Backend: Device control APIs (S4 reset, HR toggle, system restart, logs) | done | 2026-03-15 |
| E4 | Backend: Fix calories tracking in workout recorder | done | 2026-03-15 |
| E5 | Backend: Add include_hr parameter to FIT generation & upload | done | 2026-03-15 |
| E6 | Frontend: Add Settings page with device controls & Strava info | done | 2026-03-15 |
| E7 | Frontend: Add gear icon to StatusBar + navigation | done | 2026-03-15 |
| E8 | Frontend: Conditional HR tile rendering (5s timeout) | done | 2026-03-15 |
| E9 | Frontend: Add HR data checkbox to CompletionScreen upload | done | 2026-03-15 |
| E10 | Deploy: Automated Pi deployment via GitHub Actions release bundles | done | 2026-03-15 |
| E11 | Frontend: Parallax rowing animation scene between title and metrics | done | 2026-03-16 |
| E12 | Fix: HR data corruption from RR buffer lock-in, staleness too aggressive, tile disappearing | done | 2026-03-16 |
| E13 | Frontend: Replace SVG RowingScene with Pixi.js pixel art canvas renderer | done | 2026-03-17 |
| E14 | Backend: Add raw BLE HR data capture to file for debugging + fix RR corruption cross-check bug | done | 2026-03-19 |
| E15 | Frontend: Move HR out of stats grid into stroke-rate-over-time chart (dual-axis HR+SR sparkline with current HR label, show only when connected, longer grace period before hiding) | done | 2026-03-19 |
| E16 | Frontend: Fix rowing animation height on iPad landscape (too tall) | done | 2026-03-19 |
| E17 | Frontend: Simplify stats grid — remove color differentiation, reorder to: pace, stroke rate, power, time, distance, calories | done | 2026-03-19 |
| E18 | Backend: Fix workout state management — audit state machine transitions, resolve 409 Conflict errors when starting workouts after prior sessions | done | 2026-03-19 |
| E19 | Frontend: Settings — add workout state display with force-reset, fix TICKR connected tracking | done | 2026-03-19 |
| E20 | Performance review: audit CPU/memory/event-bus/rendering efficiency for Pi Zero 2W | done | 2026-03-19 |
| E21 | Backend + dashboard: generic HTTP export — POST finished workouts (JSON or FIT) to a configured URL with bearer token, retry queue in SQLite, manual send from history | done | 2026-11-14 |
| E22 | Docs: receiver guide for HTTP export (checklist, status codes, testing) + published JSON Schema kept in sync by test | done | 2026-11-14 |
