# Code Generation Plan — API Service (Background Process Visibility)

**Unit**: API Service
**Stories**: US-11.1, US-11.2, US-11.3
**Depends on**: Shared DB only (`ingestion_runs`, `recategorization_jobs`, both existing tables, no migration)

## Steps

- [x] 1. Create `api-service/src/api_service/background_activity/__init__.py`
- [x] 2. Create `background_activity/schemas.py` — `ActivitySummaryResponse`, `CurrentActivity`, `RecentActivityEntry` (per `domain-entities.md` addendum)
- [x] 3. Create `background_activity/repository.py` — `get_current_activity(db)`, `get_recent_activity(db, limit=10)` (per AR-35/36/37)
- [x] 4. Create `background_activity/service.py` — `get_activity_summary(db)` orchestrating the two repository queries into one response
- [x] 5. Create `background_activity/router.py` — `GET /background-activity/summary`, auth-protected like every other router
- [x] 6. Register `background_activity_router` in `main.py`
- [x] 7. Unit tests — `tests/test_background_activity_service.py` (repository/service-level), `tests/test_api_background_activity.py` (endpoint-level, incl. auth-required)
- [x] 8. Run full API Service unit test suite, confirm no regressions
