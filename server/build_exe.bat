@echo off
rem Genera, en server\dist:
rem   VitaMon.exe          un solo archivo (ventana, sin consola)
rem   VitaMon-windows.zip  la misma app en carpeta; da menos falsos positivos en antivirus
rem Requiere Python 3.10+ en el PATH.
cd /d "%~dp0"
if not exist .venv-build\Scripts\python.exe (
    echo Creando entorno de compilacion...
    python -m venv .venv-build || goto :error
)
.venv-build\Scripts\python -m pip install --quiet --upgrade pip
.venv-build\Scripts\python -m pip install --quiet -r requirements.txt pyinstaller pillow || goto :error

set COMMON=--noconfirm --clean --windowed --name VitaMon --icon ..\vita\sce_sys\icon0.png --add-data "..\vita\sce_sys\icon0.png;." --hidden-import pystray._win32

echo Compilando VitaMon.exe (un archivo)...
.venv-build\Scripts\python -m PyInstaller %COMMON% --onefile vitamon_gui.py || goto :error

echo Compilando version en carpeta...
if exist dist\VitaMon rmdir /s /q dist\VitaMon
.venv-build\Scripts\python -m PyInstaller %COMMON% --onedir vitamon_gui.py || goto :error
copy /y LEEME-README.txt dist\VitaMon\ >nul || goto :error
if exist dist\VitaMon-windows.zip del dist\VitaMon-windows.zip
powershell -NoProfile -Command "Compress-Archive -Path dist\VitaMon -DestinationPath dist\VitaMon-windows.zip" || goto :error

echo.
echo Listo:
echo   %~dp0dist\VitaMon.exe
echo   %~dp0dist\VitaMon-windows.zip
exit /b 0

:error
echo.
echo Error al compilar. Revisa los mensajes de arriba.
exit /b 1
