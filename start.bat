@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" goto VENV
if exist "_python.txt" goto LOCAL
set "PYEXE=pythonw"
goto RUN
:VENV
set "PYEXE=%CD%\.venv\Scripts\pythonw.exe"
goto RUN
:LOCAL
set /p PYEXE=<_python.txt
goto RUN
:RUN
start "" "%PYEXE%" "%~dp0app.py"
exit /b
