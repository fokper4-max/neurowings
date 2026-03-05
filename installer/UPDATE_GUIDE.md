# Обновления NeuroWings

Приложение проверяет обновления по адресу:

`https://193-124-117-175.nip.io/downloads/neurowings/update-feed.json`

Файлы на сервере лежат в папке:

`/opt/max-control/public/downloads/neurowings/`

## Что делать при выпуске новой версии

1. Обновить версию в:
   - `neurowings/core/constants.py`
   - `installer/installer.nsi`
   - `installer/installer_simple.nsi`
2. Собрать новый EXE на build-PC.
3. Загрузить EXE на сервер в папку:
   - `/opt/max-control/public/downloads/neurowings/`
4. Обновить `update-feed.json`.

## Пример update-feed.json

```json
{
  "app_name": "НейроКрылья",
  "version": "2.1",
  "published_at": "2026-03-05",
  "headline": "Короткое описание релиза.",
  "download_url": "https://193-124-117-175.nip.io/downloads/neurowings/NeuroWings-2.1.exe",
  "sha256": "необязательно, но желательно",
  "notes": [
    "Первое изменение.",
    "Второе изменение."
  ]
}
```

## Как это работает

- При запуске EXE приложение читает `update-feed.json`.
- Если версия новее текущей, сверху показывается плашка.
- По кнопке "Обновить" скачивается новый EXE.
- После закрытия программы новый EXE заменяет старый и приложение запускается заново.
