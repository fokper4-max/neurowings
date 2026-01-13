# Инструкции по сборке NeuroWings.exe

## Автоматическая сборка через GitHub Actions (РЕКОМЕНДУЕТСЯ)

### Шаг 1: Загрузите код на GitHub

```bash
cd /path/to/neurowings_recovere
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/neurowings.git
git push -u origin main
```

### Шаг 2: Запустите сборку

1. Зайдите на GitHub: `https://github.com/YOUR_USERNAME/neurowings`
2. Перейдите в **Actions**
3. Выберите **Build Windows EXE**
4. Нажмите **Run workflow** → **Run workflow**
5. Подождите ~10-15 минут
6. Скачайте готовый `.exe` из **Artifacts**

### Автоматическая сборка при каждом коммите

Каждый раз когда вы делаете `git push`, GitHub автоматически соберет новый .exe!

---

## Ручная сборка на Windows (если нужно)

### Вариант 1: С исправленным .spec файлом

```bash
# В корне проекта
pyinstaller NeuroWings.spec --clean
```

### Вариант 2: Базовая команда

```bash
pyinstaller --name=NeuroWings --windowed --onefile --noconfirm ^
    --add-data "neurowings;neurowings" ^
    --hidden-import=neurowings ^
    --collect-all torch ^
    --collect-all torchvision ^
    --collect-all cv2 ^
    --noupx ^
    run.py
```

---

## Исправления в этой версии

### 1. Исправлена проблема с PyTorch DLL
- ✅ Добавлен `collect_dynamic_libs()` для torch/torchvision/cv2
- ✅ Отключен UPX (ломал DLL)
- ✅ Включена консоль для отладки

### 2. Добавлен GitHub Actions workflow
- ✅ Автоматическая сборка на Windows Server
- ✅ Загрузка готового .exe как artifact
- ✅ Создание релиза при создании тега

---

## Создание релиза

Чтобы создать официальный релиз:

```bash
git tag v1.0.0
git push origin v1.0.0
```

GitHub автоматически создаст релиз с .exe файлом!

---

## Отключение консольного окна

После того как убедитесь что всё работает, в `NeuroWings.spec` измените:

```python
console=True,  # Для отладки
```

на:

```python
console=False,  # Финальная версия без консоли
```
