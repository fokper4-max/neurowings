# Ссылки для скачивания Redistributables

Если автоматическая загрузка не работает, вы можете скачать файлы вручную.

## 📥 Python Installers

### Python 3.11.8 (для Windows 10/11/12)
- **Файл:** `python-3.11.8-amd64.exe`
- **Ссылка:** https://www.python.org/ftp/python/3.11.8/python-3.11.8-amd64.exe
- **Размер:** ~26 MB
- **SHA256:** (проверьте на сайте Python)

### Python 3.10.13 (для Windows 10)
- **Файл:** `python-3.10.13-amd64.exe`
- **Ссылка:** https://www.python.org/ftp/python/3.10.13/python-3.10.13-amd64.exe
- **Размер:** ~28 MB
- **SHA256:** (проверьте на сайте Python)

### Python 3.8.18 (для Windows 8.1)
- **Файл:** `python-3.8.18-amd64.exe`
- **Ссылка:** https://www.python.org/ftp/python/3.8.18/python-3.8.18-amd64.exe
- **Размер:** ~28 MB
- **SHA256:** (проверьте на сайте Python)

## 📥 Visual C++ Redistributables

### Visual C++ 2022 Redistributable (для Windows 11/12)
- **Файл:** `vc_redist_2022_x64.exe` (переименуйте после скачивания)
- **Ссылка:** https://aka.ms/vs/17/release/vc_redist.x64.exe
- **Размер:** ~13 MB
- **Официальная страница:** https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist

### Visual C++ 2019 Redistributable (для Windows 10)
- **Файл:** `vc_redist_2019_x64.exe` (переименуйте после скачивания)
- **Ссылка:** https://aka.ms/vs/16/release/vc_redist.x64.exe
- **Размер:** ~13 MB
- **Официальная страница:** https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist

### Visual C++ 2015 Redistributable (для Windows 8.1)
- **Файл:** `vc_redist_2015_x64.exe` (используйте версию 2015-2019)
- **Ссылка:** https://aka.ms/vs/16/release/vc_redist.x64.exe
- **Размер:** ~13 MB
- **Примечание:** 2015-2019 совместимы, используйте одну и ту же ссылку

## 📁 Куда сохранять

После скачивания поместите файлы в папку:
```
installer\redistributables\
```

Структура должна быть такой:
```
installer/
└── redistributables/
    ├── python-3.8-amd64.exe
    ├── python-3.10-amd64.exe
    ├── python-3.11-amd64.exe
    ├── vc_redist_2015_x64.exe
    ├── vc_redist_2019_x64.exe
    └── vc_redist_2022_x64.exe
```

**Важно:** Имена файлов должны быть точно такими, как указано выше!

## 🔐 Проверка подлинности

### Python
Проверяйте контрольные суммы на официальной странице:
https://www.python.org/downloads/

### Visual C++ Redistributable
Скачивайте только с официальных ссылок Microsoft (aka.ms):
- https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist

## 🚀 Автоматическая загрузка

Вместо ручной загрузки рекомендуется использовать скрипт:

```powershell
cd "C:\NeuroWings 2.0\installer"
.\download_redistributables.ps1
```

Скрипт автоматически:
- Создаст папку `redistributables`
- Скачает все необходимые файлы
- Проверит наличие уже загруженных файлов
- Покажет размеры файлов

## 📊 Альтернативные источники

### Chocolatey (Windows Package Manager)

Если у вас установлен Chocolatey:

```powershell
# Python
choco install python --version=3.11.8 -y

# Visual C++ Redistributable
choco install vcredist2022 -y
```

### WinGet (Windows Package Manager)

Если у вас Windows 10/11 с WinGet:

```powershell
# Python
winget install Python.Python.3.11

# Visual C++ Redistributable
winget install Microsoft.VCRedist.2022.x64
```

**Примечание:** Эти методы установят зависимости в систему, но не загрузят установщики для инсталлятора.

## ⚠️ Важные замечания

### Версии Python
- Для Windows 8.1 максимум Python 3.8
- Для Windows 10 рекомендуется Python 3.10
- Для Windows 11/12 рекомендуется Python 3.11

### Visual C++ Redistributable
- VC++ 2015, 2017, 2019 совместимы (используют одну и ту же базу)
- VC++ 2022 - самая новая версия
- Для PyTorch требуется VC++ 2015+ (любая версия)

### Архитектура
- ⚠️ Только x64 (64-bit) версии!
- ❌ x86 (32-bit) НЕ поддерживается
- Инсталлятор проверяет архитектуру автоматически

## 🔄 Обновление ссылок

Этот файл актуален на дату: **2025-02-06**

Если ссылки устарели:
1. Python: https://www.python.org/downloads/
2. VC++ Redistributable: https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist

## 📞 Помощь

Если возникли проблемы с загрузкой:
1. Проверьте интернет-соединение
2. Попробуйте другой браузер
3. Скачайте с альтернативных источников
4. Создайте issue: https://github.com/yourusername/neurowings/issues

---

**Дата обновления:** 2025-02-06
**Версия:** 1.0
