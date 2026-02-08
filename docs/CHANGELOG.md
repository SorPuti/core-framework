# Changelog

All notable changes to Core Framework.

## [0.14.0] - Latest

### Added
- Admin panel with Django-style ModelAdmin
- User-definable theme (dark/light mode)
- Operations section for superusers only

### Changed
- Improved M2M field handling in admin
- Better permission-based UI visibility

## [0.13.0]

### Added
- Single source of truth for settings (`src/settings.py`)
- Auto-configuration of auth and datetime from settings
- Simplified bootstrap lifecycle

### Changed
- Removed `configure_auth()` and `configure_datetime()` from main.py
- Settings now drive all configuration

### Migration
See `docs/archive/36-migration-guide-0.13.md`

## [0.12.27]

### Fixed
- Kafka backend improvements
- Worker stability fixes

## [0.12.3]

### Added
- Django-style middleware system
- Testing utilities

## [0.12.2]

### Fixed
- Various bug fixes
- Middleware improvements

### Migration
See `docs/archive/32-migration-guide-0.12.2.md`

---

For detailed changelogs, see `docs/archive/`.
