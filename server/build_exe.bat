@echo off
rem Genera server\dist\VitaMon.exe (ventana, sin consola). Requiere Python 3.10+ en el PATH.
cd /d "%~dp0"
if not exist .venv-build\Scripts\python.exe (
    echo Creando entorno de compilacion...
    python -m venv .venv-build || goto :error
)
.venv-build\Scripts\python -m pip install --quiet --upgrade pip
.venv-build\Scripts\python -m pip install --quiet -r requirements.txt pyinstaller pillow || goto :error
.venv-build\Scripts\python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name VitaMon ^
    --icon ..\vita\sce_sys\icon0.png ^
    --add-data "..\vita\sce_sys\icon0.png;." ^
    vitamon_gui.py || goto :error
echo.
echo Listo: %~dp0dist\VitaMon.exe
exit /b 0

:error
echo.
echo Error al compilar. Revisa los mensajes de arriba.
exit /b 1
