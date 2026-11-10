@echo off
rem Inicia el servidor VitaMon. Si usas un venv en server\.venv, se activa solo.
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
python vitamon_server.py %*
