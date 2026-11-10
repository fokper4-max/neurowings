# Changelog

## [2.2.2] - 2026-11-10

- Округление координат `.tps` до целых пикселей `,00000` и `ID=0` для 100% совместимости с Excel Карташова в. 2.5 и TPSDig264.
- Автоматическое исправление старых `.tps` и `.nw.json` при открытии папки или изображения.
- Точное совпадение расчёта `m` (SEM) и баллов с формулами Excel Карташова в. 2.5.
- Улучшенный скрипт автообновления `updater.ps1` с ожиданием освобождения файла PyInstaller OneFile.

## [2.1.0] - 2026-11-02

- Canonical EXIF image coordinates, validated atomic TPS with fractional precision.
- Safer processing lifecycle, aggregate analysis, coherent batch statistics and editing.
- Corrected boundary crops, statistical edge cases, Excel/graphs packaging and startup diagnostics.
- HTTPS/checksum update validation and strict publication host verification.
- Preserve wing identities during redraw, reject missing/degenerate landmarks and unavailable sources.
- Atomic cross-platform XLSX without modifying TPS; original-resolution low-memory annotated exports.

# Changelog

All notable changes to the source repository will be documented in this file.

The format follows Keep a Changelog and the repository uses Semantic Versioning
for Git tags.

## [2.0.0] - 2026-03-05

### Added

- Initial source repository for NeuroWings
- Application code, packaging scripts, and model usage instructions
- Repository-level Git ignore rules for source-only publishing

### Excluded

- Trained model weights from version control
- Local build outputs, caches, logs, and machine-specific artifacts
- Large `drivers/` assets that are not part of the application source
