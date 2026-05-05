@echo off
cd /d "%~dp0"

echo Iniciando Sistema de Corrida RC...
echo.
echo O sistema vai abrir:
echo - Servidor WebSocket
echo - Painel web no navegador
echo - Deteccao pela camera com OpenCV
echo.
echo Para encerrar a deteccao, pressione ESC na janela da camera.
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    py Main.py
) else (
    python Main.py
)

echo.
echo Sistema encerrado.
pause
