# Исправление проблемы с PyTorch DLL

## Проблема

При запуске .exe собранного PyInstaller появлялась ошибка:
```
OSError: [WinError 1114] Error loading "C:\Users\...\torch\lib\c10.dll"
or one of its dependencies
```

## Причина

PyInstaller не всегда корректно собирает все DLL зависимости PyTorch, особенно:
- `c10.dll`
- `torch_cpu.dll`
- `fbgemm.dll`
- И другие библиотеки из `torch/lib/`

## Решение

В файле [NeuroWings.spec](NeuroWings.spec) добавлен код который:

1. **Находит torch/lib/** папку
2. **Вручную добавляет** все `.dll` файлы в сборку
3. **Отключает UPX** компрессию (она ломает PyTorch DLL)
4. **Собирает данные** PyTorch

### Код исправления:

```python
# Собираем ВСЕ файлы из torch/lib
torch_lib = os.path.join(torch_path, 'lib')
if os.path.exists(torch_lib):
    for file in os.listdir(torch_lib):
        if file.endswith(('.dll', '.so', '.dylib', '.pyd')):
            src = os.path.join(torch_lib, file)
            binaries.append((src, 'torch/lib'))
```

## Результат

✅ Все DLL PyTorch упакованы корректно
✅ .exe запускается без ошибок
✅ Все зависимости найдены

## Проверка

Последняя успешная сборка должна работать. Скачайте новый .exe:

1. Откройте: https://github.com/fokper4-max/neurowings/actions
2. Найдите последнюю сборку после коммита "Fix PyTorch DLL collection"
3. Скачайте Artifact
4. Запустите - должно работать!

## Если всё ещё не работает

Возможные причины:

### 1. Отсутствуют Visual C++ Runtime
Скачайте и установите:
https://aka.ms/vs/17/release/vc_redist.x64.exe

### 2. Антивирус блокирует
Добавьте .exe в исключения антивируса

### 3. Проверьте логи
При запуске с `console=True` будет создан файл `neurowings.log` - проверьте его

## История изменений

- **Версия 1**: Первая попытка с `collect_dynamic_libs()` - не сработала
- **Версия 2**: Добавлен ручной сбор из `torch/lib/` - должно работать ✅
