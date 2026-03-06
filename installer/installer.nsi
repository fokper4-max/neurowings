; НейроКрылья NSIS Installer Script
; Автоматически определяет версию Windows и устанавливает необходимые зависимости

;--------------------------------
; Настройки

!define PRODUCT_NAME "НейроКрылья"
!define PRODUCT_VERSION "2.0.3"
!define PRODUCT_PUBLISHER "Команда НейроКрылья"
!define PRODUCT_WEB_SITE "https://github.com/yourusername/neurowings"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
!define PRODUCT_UNINST_ROOT_KEY "HKLM"

; Современный интерфейс
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!include "WinVer.nsh"

; Название инсталлятора
Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "..\dist\${PRODUCT_NAME}-${PRODUCT_VERSION}-Setup.exe"

; Директория установки по умолчанию
InstallDir "$PROGRAMFILES64\${PRODUCT_NAME}"

; Запрос прав администратора
RequestExecutionLevel admin

;--------------------------------
; Переменные

Var WindowsVersion
Var PythonNeeded
Var VCRedistNeeded
Var PythonVersion
Var VCRedistVersion

;--------------------------------
; Страницы интерфейса

!define MUI_ABORTWARNING
!define MUI_ICON "..\neurowings\assets\app_icon.ico"
!define MUI_UNICON "..\neurowings\assets\app_icon.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\LICENSE.txt"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Russian"
!insertmacro MUI_LANGUAGE "English"

;--------------------------------
; Функция определения версии Windows

Function DetectWindowsVersion
    ; Определяем версию Windows
    ${If} ${AtLeastWin10}
        ; Windows 10 или 11/12
        ReadRegStr $0 HKLM "SOFTWARE\Microsoft\Windows NT\CurrentVersion" "CurrentBuild"

        ${If} $0 >= 22000
            ${If} $0 >= 24000
                StrCpy $WindowsVersion "Windows 12"
                StrCpy $PythonVersion "3.11"
                StrCpy $VCRedistVersion "2022"
            ${Else}
                StrCpy $WindowsVersion "Windows 11"
                StrCpy $PythonVersion "3.11"
                StrCpy $VCRedistVersion "2022"
            ${EndIf}
        ${Else}
            StrCpy $WindowsVersion "Windows 10"
            StrCpy $PythonVersion "3.10"
            StrCpy $VCRedistVersion "2019"
        ${EndIf}
    ${ElseIf} ${IsWin8.1}
        StrCpy $WindowsVersion "Windows 8.1"
        StrCpy $PythonVersion "3.8"
        StrCpy $VCRedistVersion "2015"
    ${Else}
        MessageBox MB_ICONSTOP "Windows 8.1 или новее требуется для установки ${PRODUCT_NAME}"
        Abort
    ${EndIf}

    DetailPrint "Обнаружена версия: $WindowsVersion"
    DetailPrint "Рекомендуемая версия Python: $PythonVersion"
    DetailPrint "Рекомендуемая версия VC++ Redistributable: $VCRedistVersion"
FunctionEnd

;--------------------------------
; Функция проверки Python

Function CheckPython
    ; Проверяем наличие Python 3.8+
    StrCpy $PythonNeeded "0"

    nsExec::ExecToStack 'python --version'
    Pop $0 ; Код возврата
    Pop $1 ; Вывод

    ${If} $0 != 0
        StrCpy $PythonNeeded "1"
        DetailPrint "Python не найден"
    ${Else}
        DetailPrint "Python обнаружен: $1"

        ; Проверяем версию (нужен 3.8+)
        ${If} $1 S< "Python 3.8"
            StrCpy $PythonNeeded "1"
            DetailPrint "Версия Python устарела, требуется обновление"
        ${EndIf}
    ${EndIf}
FunctionEnd

;--------------------------------
; Функция проверки Visual C++ Redistributable

Function CheckVCRedist
    StrCpy $VCRedistNeeded "0"

    ; Проверяем наличие VC++ 2015-2022
    ClearErrors
    ReadRegStr $0 HKLM "SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" "Version"

    ${If} ${Errors}
        StrCpy $VCRedistNeeded "1"
        DetailPrint "Visual C++ Redistributable не найден"
    ${Else}
        DetailPrint "Visual C++ Redistributable обнаружен: $0"
    ${EndIf}
FunctionEnd

;--------------------------------
; Секции установки

Section "Основная программа" SecMain
    SectionIn RO  ; Обязательная секция

    SetOutPath "$INSTDIR"

    ; Копируем основной exe файл
    File "..\dist\${PRODUCT_NAME}.exe"

    ; Создаем ярлыки
    CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_NAME}.exe"
    CreateShortCut "$DESKTOP\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_NAME}.exe"

    ; Записываем информацию для деинсталлятора
    WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayName" "${PRODUCT_NAME}"
    WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\uninstall.exe"
    WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
    WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
    WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"

    WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd

Section "Python Runtime" SecPython
    ${If} $PythonNeeded == "1"
        DetailPrint "Установка Python $PythonVersion..."

        SetOutPath "$TEMP"

        ; Скачиваем и устанавливаем Python
        ${If} $PythonVersion == "3.11"
            ; Python 3.11 для Windows 10/11/12
            File "redistributables\python-3.11-amd64.exe"
            ExecWait '"$TEMP\python-3.11-amd64.exe" /quiet InstallAllUsers=1 PrependPath=1' $0
        ${ElseIf} $PythonVersion == "3.10"
            ; Python 3.10 для Windows 10
            File "redistributables\python-3.10-amd64.exe"
            ExecWait '"$TEMP\python-3.10-amd64.exe" /quiet InstallAllUsers=1 PrependPath=1' $0
        ${ElseIf} $PythonVersion == "3.8"
            ; Python 3.8 для Windows 8.1
            File "redistributables\python-3.8-amd64.exe"
            ExecWait '"$TEMP\python-3.8-amd64.exe" /quiet InstallAllUsers=1 PrependPath=1' $0
        ${EndIf}

        ${If} $0 != 0
            MessageBox MB_ICONEXCLAMATION "Ошибка установки Python. Код: $0"
        ${Else}
            DetailPrint "Python успешно установлен"
        ${EndIf}
    ${Else}
        DetailPrint "Python уже установлен, пропускаем"
    ${EndIf}
SectionEnd

Section "Visual C++ Redistributable" SecVCRedist
    ${If} $VCRedistNeeded == "1"
        DetailPrint "Установка Visual C++ Redistributable $VCRedistVersion..."

        SetOutPath "$TEMP"

        ; Устанавливаем соответствующую версию VC++ Redistributable
        ${If} $VCRedistVersion == "2022"
            File "redistributables\vc_redist_2022_x64.exe"
            ExecWait '"$TEMP\vc_redist_2022_x64.exe" /quiet /norestart' $0
        ${ElseIf} $VCRedistVersion == "2019"
            File "redistributables\vc_redist_2019_x64.exe"
            ExecWait '"$TEMP\vc_redist_2019_x64.exe" /quiet /norestart' $0
        ${ElseIf} $VCRedistVersion == "2015"
            File "redistributables\vc_redist_2015_x64.exe"
            ExecWait '"$TEMP\vc_redist_2015_x64.exe" /quiet /norestart' $0
        ${EndIf}

        ${If} $0 != 0
            ${If} $0 == 3010
                DetailPrint "VC++ Redistributable установлен, требуется перезагрузка"
            ${Else}
                MessageBox MB_ICONEXCLAMATION "Ошибка установки VC++ Redistributable. Код: $0"
            ${EndIf}
        ${Else}
            DetailPrint "VC++ Redistributable успешно установлен"
        ${EndIf}
    ${Else}
        DetailPrint "VC++ Redistributable уже установлен, пропускаем"
    ${EndIf}
SectionEnd

;--------------------------------
; Описания секций

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} "Основные файлы программы ${PRODUCT_NAME}"
    !insertmacro MUI_DESCRIPTION_TEXT ${SecPython} "Python runtime (будет установлен только если отсутствует)"
    !insertmacro MUI_DESCRIPTION_TEXT ${SecVCRedist} "Visual C++ Redistributable (требуется для работы PyTorch)"
!insertmacro MUI_FUNCTION_DESCRIPTION_END

;--------------------------------
; Обработчики событий

Function .onInit
    ; Проверяем 64-битную систему
    ${IfNot} ${RunningX64}
        MessageBox MB_ICONSTOP "Эта программа требует 64-битную версию Windows"
        Abort
    ${EndIf}

    ; Определяем версию Windows
    Call DetectWindowsVersion

    ; Проверяем зависимости
    Call CheckPython
    Call CheckVCRedist

    ; Показываем информацию
    MessageBox MB_ICONINFORMATION "Система: $WindowsVersion$\n\
        Python: $PythonNeeded (0=установлен, 1=требуется)$\n\
        VC++ Redist: $VCRedistNeeded (0=установлен, 1=требуется)"
FunctionEnd

;--------------------------------
; Деинсталлятор

Section "Uninstall"
    ; Удаляем файлы
    Delete "$INSTDIR\${PRODUCT_NAME}.exe"
    Delete "$INSTDIR\uninstall.exe"

    ; Удаляем ярлыки
    Delete "$SMPROGRAMS\${PRODUCT_NAME}\${PRODUCT_NAME}.lnk"
    Delete "$DESKTOP\${PRODUCT_NAME}.lnk"
    RMDir "$SMPROGRAMS\${PRODUCT_NAME}"

    ; Удаляем директорию
    RMDir "$INSTDIR"

    ; Удаляем записи реестра
    DeleteRegKey ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}"

    SetAutoClose true
SectionEnd

Function un.onInit
    MessageBox MB_ICONQUESTION|MB_YESNO|MB_DEFBUTTON2 \
        "Вы уверены, что хотите удалить $(^Name) и все его компоненты?" \
        IDYES +2
    Abort
FunctionEnd
