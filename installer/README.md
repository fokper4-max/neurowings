# NeuroWings Installer - Документация по сборке

## Описание

Система автоматической сборки инсталлятора NeuroWings для Windows. Инсталлятор автоматически:
- **Определяет версию Windows** (8.1, 10, 11, 12+)
- **Устанавливает Python** подходящей версии (если отсутствует)
- **Устанавливает Visual C++ Redistributable** для работы PyTorch (если отсутствует)
- **Устанавливает NeuroWings** с созданием ярлыков

## Поддерживаемые версии Windows

| Windows Version | Python Version | VC++ Redist Version |
|----------------|----------------|---------------------|
| Windows 8.1    | 3.8.18         | 2015                |
| Windows 10     | 3.10.13        | 2019                |
| Windows 11     | 3.11.8         | 2022                |
| Windows 12+    | 3.11.8         | 2022                |

## Структура файлов

```
installer/
├── NeuroWings.spec              # PyInstaller спецификация
├── installer.nsi                # NSIS скрипт инсталлятора
├── build_installer.ps1          # PowerShell скрипт сборки
├── build_installer.bat          # BAT обертка для запуска
├── download_redistributables.ps1 # Скрипт загрузки зависимостей
├── redistributables/            # Папка с загруженными файлами
│   ├── python-3.8-amd64.exe
│   ├── python-3.10-amd64.exe
│   ├── python-3.11-amd64.exe
│   ├── vc_redist_2015_x64.exe
│   ├── vc_redist_2019_x64.exe
│   └── vc_redist_2022_x64.exe
└── README.md                    # Этот файл
```

## Требования для сборки

### Обязательные компоненты:

1. **Python 3.8+** с pip
   - Скачать: https://www.python.org/downloads/
   - При установке отметить "Add Python to PATH"

2. **NSIS 3.x** (Nullsoft Scriptable Install System)
   - Скачать: https://nsis.sourceforge.io/Download
   - Установить в стандартное расположение: `C:\Program Files (x86)\NSIS\`

3. **Права администратора** для запуска скриптов

### Установка зависимостей Python:

```powershell
# Переход в корень проекта
cd "C:\NeuroWings 2.0"

# Установка зависимостей
pip install -r requirements.txt
```

## Процесс сборки

### Метод 1: Автоматическая сборка (рекомендуется)

Самый простой способ - дважды кликнуть на файл:

```
installer\build_installer.bat
```

Скрипт автоматически:
1. Запросит права администратора
2. Загрузит redistributables
3. Установит PyInstaller (если нужно)
4. Соберет EXE с PyInstaller
5. Создаст инсталлятор с NSIS

### Метод 2: PowerShell с опциями

```powershell
# Переход в папку installer
cd "C:\NeuroWings 2.0\installer"

# Полная сборка
.\build_installer.ps1

# Сборка с очисткой старых файлов
.\build_installer.ps1 -Clean

# Сборка с внешней папкой моделей (основной вариант для build-сервера)
.\build_installer.ps1 -ModelsDir "C:\ProgramData\NeuroWingsBuilder\models-source"

# Пропустить загрузку redistributables (если уже загружены)
.\build_installer.ps1 -SkipDownload

# Только сборка NSIS (если EXE уже готов)
.\build_installer.ps1 -SkipPyInstaller

# Только PyInstaller (без NSIS)
.\build_installer.ps1 -SkipNSIS
```

### Метод 3: Пошаговая сборка

#### Шаг 1: Загрузка redistributables

```powershell
cd "C:\NeuroWings 2.0\installer"
.\download_redistributables.ps1
```

Скрипт загрузит:
- Python 3.8, 3.10, 3.11 (64-bit)
- Visual C++ 2015, 2019, 2022 (64-bit)

Файлы будут сохранены в `installer\redistributables\`

#### Шаг 2: Сборка EXE с PyInstaller

```powershell
cd "C:\NeuroWings 2.0"
pyinstaller --clean --noconfirm installer\NeuroWings.spec
```

Результат: `dist\NeuroWings.exe`

#### Шаг 3: Сборка инсталлятора с NSIS

```powershell
cd "C:\NeuroWings 2.0\installer"
"C:\Program Files (x86)\NSIS\makensis.exe" installer.nsi
```

Результат: `dist\NeuroWings-2.0-Setup.exe`

## Результаты сборки

После успешной сборки в папке `dist\` будут находиться:

- **NeuroWings.exe** - Автономный исполняемый файл приложения (~500+ MB)
- **NeuroWings-2.0-Setup.exe** - Инсталлятор с зависимостями (~600+ MB)

## Тестирование инсталлятора

### Рекомендуемый процесс тестирования:

1. **Тест на чистой системе** (виртуальная машина)
   - Создайте VM с чистым Windows
   - Запустите `NeuroWings-2.0-Setup.exe`
   - Проверьте установку всех зависимостей

2. **Тест на разных версиях Windows**
   - Windows 8.1 (Python 3.8, VC++ 2015)
   - Windows 10 (Python 3.10, VC++ 2019)
   - Windows 11 (Python 3.11, VC++ 2022)

3. **Тест с существующими зависимостями**
   - Установите Python вручную
   - Запустите инсталлятор
   - Убедитесь, что он пропускает установку Python

4. **Тест функционала приложения**
   - Загрузка изображений
   - Обработка с нейросетями
   - Экспорт результатов

## Настройка инсталлятора

### Изменение версии

Отредактируйте `installer\installer.nsi`:

```nsis
!define PRODUCT_VERSION "2.0"  ; <- изменить здесь
```

### Добавление иконки

1. Создайте файл `icon.ico`
2. Поместите в корень проекта
3. Отредактируйте `installer\NeuroWings.spec`:

```python
icon='icon.ico'  # <- раскомментировать и указать путь
```

### Изменение директории установки

Отредактируйте `installer\installer.nsi`:

```nsis
InstallDir "$PROGRAMFILES64\${PRODUCT_NAME}"  ; <- изменить здесь
```

### Добавление дополнительных файлов

Отредактируйте `installer\NeuroWings.spec`:

```python
datas = [
    (str(models_dir), 'models'),
    ('config.ini', '.'),          # <- добавить здесь
    ('docs', 'docs'),             # <- папку docs
]
```

## Распространение инсталлятора

### Размещение файлов:

1. **GitHub Releases**
   ```bash
   # Создать release с тегом
   git tag -a v2.0 -m "Release version 2.0"
   git push origin v2.0
   ```

2. **Google Drive / Dropbox**
   - Загрузить `NeuroWings-2.0-Setup.exe`
   - Создать публичную ссылку

3. **Собственный сервер**
   ```bash
   # Копирование на сервер
   scp dist/NeuroWings-2.0-Setup.exe user@server:/var/www/downloads/
   ```

### Контрольная сумма (MD5/SHA256):

```powershell
# Вычисление SHA256
certutil -hashfile "dist\NeuroWings-2.0-Setup.exe" SHA256

# Сохранение в файл
certutil -hashfile "dist\NeuroWings-2.0-Setup.exe" SHA256 > "dist\NeuroWings-2.0-Setup.exe.sha256"
```

## Устранение неполадок

### Ошибка: "Python не найден"

**Решение:**
1. Установите Python 3.8+ с https://www.python.org/
2. Убедитесь, что отмечен "Add Python to PATH"
3. Перезапустите терминал

### Ошибка: "NSIS не найден"

**Решение:**
1. Установите NSIS с https://nsis.sourceforge.io/
2. Убедитесь, что установлен в `C:\Program Files (x86)\NSIS\`
3. Или измените путь в `build_installer.ps1`

### Ошибка: "PyInstaller failed"

**Возможные причины:**
- Отсутствуют зависимости: `pip install -r requirements.txt`
- Антивирус блокирует: добавьте проект в исключения
- Недостаточно места: освободите место на диске

**Решение:**
```powershell
# Очистка и повторная сборка
.\build_installer.ps1 -Clean
```

### Ошибка: "Redistributables не загружены"

**Решение:**
```powershell
# Принудительная перезагрузка
.\download_redistributables.ps1 -Force
```

### Инсталлятор не запускается на целевой системе

**Проверьте:**
1. 64-битная ли система? (инсталлятор требует x64)
2. Windows 8.1 или новее?
3. Есть ли права администратора?

## Автоматизация CI/CD

### GitHub Actions пример:

```yaml
name: Build Installer

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    runs-on: windows-latest

    steps:
    - uses: actions/checkout@v3

    - name: Setup Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: pip install -r requirements.txt

    - name: Install NSIS
      run: choco install nsis -y

    - name: Build installer
      run: .\installer\build_installer.bat

    - name: Upload artifact
      uses: actions/upload-artifact@v3
      with:
        name: installer
        path: dist\NeuroWings-2.0-Setup.exe
```

## Лицензия

MIT License - см. файл LICENSE.txt в корне проекта

## Поддержка

При возникновении проблем:
1. Проверьте логи сборки
2. Убедитесь, что установлены все требования
3. Создайте issue на GitHub с описанием проблемы

---

**Дата обновления:** 2025-02-06
**Версия документа:** 1.0
