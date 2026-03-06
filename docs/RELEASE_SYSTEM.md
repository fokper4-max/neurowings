# Схема релизов и обновлений NeuroWings

Этот документ описывает рабочую схему сборки, публикации, обновлений и хранения документации без паролей и других секретов.

## 1. Источник правды

- Код и документация хранятся в GitHub-репозитории `main`.
- Ноутбук хранит те же файлы локально в рабочем репозитории.
- Windows build server автоматически подтягивает новые коммиты из GitHub.
- Linux update server хранит опубликованные `exe`, `update-feed.json` и копию документации.

## 2. Серверы и роли

### Windows build server

- Назначение: сборка `EXE` и публикация релизов.
- Рабочая папка билдера: `C:\ProgramData\NeuroWingsBuilder`
- Репозиторий билдера: `C:\ProgramData\NeuroWingsBuilder\repo\NeuroWings`
- Внешняя папка моделей: `C:\ProgramData\NeuroWingsBuilder\models-source`
- Планировщик Windows запускает задачу `NeuroWings Release Agent`.

### Linux update server

- Назначение: публичная раздача релизов и документации.
- Базовая папка публикации: `/opt/max-control/public/downloads/neurowings`
- Публичный URL релизов: `https://193-124-117-175.nip.io/downloads/neurowings`
- Публичный feed обновлений: `https://193-124-117-175.nip.io/downloads/neurowings/update-feed.json`

## 3. Что публикуется на Linux server

- `NeuroWings-latest.exe`
- `NeuroWings-{version}.exe`
- `NeuroWings-latest-Setup.exe` при наличии setup
- `NeuroWings-{version}-Setup.exe` при наличии setup
- `update-feed.json`
- папка `docs/`
- `docs/index.json`

## 4. Документация

На сервер автоматически выгружаются:

- `README.md`
- `CHANGELOG.md`
- `installer/README.md`
- `installer/UPDATE_GUIDE.md`
- `installer/CHANGELOG.md`
- `models/README.txt`
- `docs/RELEASE_SYSTEM.md`

Публичный индекс документации:

- `https://193-124-117-175.nip.io/downloads/neurowings/docs/index.json`

## 5. Автоматическая логика

### Если меняется `APP_VERSION`

1. Windows agent видит новый коммит в `main`.
2. Агент обновляет локальный репозиторий билдера.
3. Агент использует модели из `C:\ProgramData\NeuroWingsBuilder\models-source`.
4. Собирается новый `EXE`.
5. Релиз публикуется на Linux server.
6. Вместе с релизом публикуется документация.
7. `update-feed.json` обновляется до новой версии.

### Если `APP_VERSION` не меняется

1. Windows agent все равно подтягивает новый коммит из `main`.
2. Полная сборка не запускается.
3. Агент выполняет только синхронизацию документации.
4. Папка `docs/` на Linux server обновляется автоматически.

## 6. Как работает обновление у пользователя

1. Пользователь запускает `EXE`.
2. Программа читает `update-feed.json`.
3. Если на сервере версия новее локальной, показывается уведомление об обновлении.
4. По кнопке обновления скачивается свежий `EXE`.
5. После перезапуска пользователь работает уже на новой версии.

## 7. Модели

- Модели не хранятся в GitHub.
- Модели не тянутся пользователем отдельно.
- Они берутся билд-сервером из внешней папки и встраиваются в релиз.
- За счет этого пользователь скачивает один готовый `EXE`.

## 8. Ограничения

- На Windows build server только `1 GB RAM`, поэтому сборка тяжелого `EXE` может идти долго.
- Документация синхронизируется быстрее, потому что не требует PyInstaller.
- Публикация не хранит пароли в документации и не выгружает секреты на публичный сервер.

## 9. Практический результат

- На ноутбуке документация живет прямо в репозитории.
- На Windows build server документация обновляется через `git pull`.
- На Linux update server документация обновляется через автоматическую публикацию.
- У схемы теперь один источник правды: GitHub `main`.
