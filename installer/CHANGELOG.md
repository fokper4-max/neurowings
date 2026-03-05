# Changelog - NeuroWings Installer System

Все важные изменения в системе инсталлятора будут документироваться в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/),
версионирование согласно [Semantic Versioning](https://semver.org/lang/ru/).

## [1.0.0] - 2025-02-06

### Добавлено
- 🎉 Первая версия системы автоматической сборки инсталлятора
- ✨ PyInstaller спецификация для упаковки в standalone EXE
- ✨ NSIS инсталлятор с автоматическим определением версии Windows
- ✨ Автоматическая установка Python (3.8/3.10/3.11) в зависимости от Windows
- ✨ Автоматическая установка Visual C++ Redistributable (2015/2019/2022)
- ✨ PowerShell скрипт полной автоматической сборки
- ✨ BAT обертка для простого запуска
- ✨ PowerShell скрипт загрузки redistributables
- 📖 Полная документация для разработчиков (README.md)
- 📖 Руководство пользователя (USER_GUIDE.md)
- 📖 Быстрый старт (QUICKSTART.md)
- 📖 Резюме системы (SUMMARY.md)
- 📖 Ссылки для скачивания (DOWNLOAD_LINKS.md)
- 🔧 .gitignore для исключения больших файлов
- 🎯 Создание ярлыков (рабочий стол + меню Пуск)
- 🎯 Регистрация деинсталлятора в системе

### Поддержка Windows версий
- ✅ Windows 8.1 → Python 3.8 + VC++ 2015
- ✅ Windows 10 → Python 3.10 + VC++ 2019
- ✅ Windows 11 → Python 3.11 + VC++ 2022
- ✅ Windows 12+ → Python 3.11 + VC++ 2022

### Технические детали
- PyInstaller: Создание standalone EXE (~500+ MB)
- NSIS: Создание setup инсталлятора (~600+ MB)
- Архитектура: Только x64 (64-bit)
- Языки интерфейса: Русский, English

### Зависимости
- Python 3.8+ (для сборки)
- NSIS 3.x (для сборки инсталлятора)
- PyInstaller 6.0+ (автоматически устанавливается)

### Структура проекта
```
installer/
├── NeuroWings.spec              # PyInstaller спецификация
├── installer.nsi                # NSIS скрипт
├── build_installer.ps1          # Главный скрипт сборки
├── build_installer.bat          # BAT запускатель
├── download_redistributables.ps1 # Загрузчик зависимостей
├── .gitignore                   # Git игнор
├── README.md                    # Документация разработчика
├── USER_GUIDE.md                # Руководство пользователя
├── QUICKSTART.md                # Быстрый старт
├── SUMMARY.md                   # Резюме
├── DOWNLOAD_LINKS.md            # Ссылки для загрузки
└── CHANGELOG.md                 # Этот файл
```

---

## Планы на будущее

### [1.1.0] - Планируется
- [ ] Добавление иконки приложения
- [ ] Поддержка silent установки (`/S` флаг)
- [ ] Выбор языка при установке
- [ ] Ассоциация файлов (.tps, .nxs)
- [ ] Проверка обновлений при запуске
- [ ] Portable версия (без установки)

### [1.2.0] - Идеи
- [ ] Code signing сертификат (для антивирусов)
- [ ] Интеграция с GitHub Actions CI/CD
- [ ] Автоматическое создание release на GitHub
- [ ] Multilingual interface (EN, RU, DE, FR)
- [ ] MSI installer в дополнение к NSIS
- [ ] Chocolatey package
- [ ] WinGet package

### [2.0.0] - Будущее
- [ ] Auto-update система
- [ ] Telemetry и crash reporting (опционально)
- [ ] Plugin system для расширений
- [ ] Web-based installer (online installer)
- [ ] Microsoft Store version
- [ ] macOS и Linux версии

---

## История изменений (будет дополняться)

### Формат записей:

#### Added (Добавлено)
- Новые функции

#### Changed (Изменено)
- Изменения в существующем функционале

#### Deprecated (Устарело)
- Функции, которые скоро будут удалены

#### Removed (Удалено)
- Удаленные функции

#### Fixed (Исправлено)
- Исправления багов

#### Security (Безопасность)
- Исправления уязвимостей

---

## Как вносить изменения

При внесении изменений в систему инсталлятора:

1. Обновите этот файл (CHANGELOG.md)
2. Укажите дату и версию
3. Опишите изменения в соответствующем разделе
4. Обновите версию в installer.nsi:
   ```nsis
   !define PRODUCT_VERSION "X.Y.Z"
   ```

---

## Контакты

- **Проект:** NeuroWings
- **Репозиторий:** https://github.com/yourusername/neurowings
- **Issues:** https://github.com/yourusername/neurowings/issues
- **Wiki:** https://github.com/yourusername/neurowings/wiki

---

**Поддерживается с:** 2025-02-06
**Текущая версия:** 1.0.0
**Статус:** ✅ Stable
