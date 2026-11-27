# Changelog

All notable changes to the source repository will be documented in this file.

The format follows Keep a Changelog and the repository uses Semantic Versioning
for Git tags.

## [2.3.0] - 2026-11-27

### Added

- Инструмент «✂ Ножницы» (`EditMode.SPLIT`, клавиша `C`) для разрезания многосемейных сканов (5-10 семей на одном листе А4) прямо в программе без изменения исходного файла и с сохранением DPI.
- Автоматический поиск полос и сетки семей (`detect_family_regions`) с фильтрацией этикеток и подсказкой оптимального поворота крыльев (`↺ 90° влево`, `↻ 90° вправо`, `180°`).
- Поворот текущего скана на 90° влево (`↺ -90°`) с синхронным пересчётом координат точек и рамок крыльев.
- Прокси-отображение сверхбольших сканов 432+ МП (`read_pixmap_for_display`) для стабильной и быстрой работы интерфейса без переполнения памяти.
- Удаление файлов из левого списка (кнопка «🗑», контекстное меню, «Файл -> Убрать текущий файл из списка», `Ctrl+W`) без удаления исходных файлов с диска и с пересчётом сводной статистики.

### Changed

- Синхронизированы версии и метаданные сборки (`constants.py`, NSIS-установщики, спецификации PyInstaller) и обновлена памятка пчеловода.

### Fixed

- Калибровка точек по осям жилок в режиме «⬜ Рамка» (`recognize_wing_in_bbox`) приведена в соответствие с основным пайплайном распознавания.
- Удаление последнего крыла корректно перезаписывает пустой `.tps` и обновляет статус и счётчик обработанных файлов в левой панели.
- Санитайзер имён вырезаемых семей (`sanitize_region_name`) защищает от зарезервированных имён Windows, включая имена с расширением (например, `CON.txt` -> `CON_1.txt`).
- Поддержана досрочная остановка нарезки через `should_stop` в `split_image_regions` и фоновом `SplitWorker` без создания лишних файлов.
- Удалены дубликаты `'PIL.AvifImagePlugin'` и `'PIL._avif'` в `excludes` файлов `NeuroWings.spec` и `NeuroWings_onedir.spec`, исправлен URL проекта в NSIS-скриптах.

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

## [2.0.0] - 2026-03-05

### Added

- Initial source repository for NeuroWings
- Application code, packaging scripts, and model usage instructions
- Repository-level Git ignore rules for source-only publishing

### Excluded

- Trained model weights from version control
- Local build outputs, caches, logs, and machine-specific artifacts
- Large `drivers/` assets that are not part of the application source
