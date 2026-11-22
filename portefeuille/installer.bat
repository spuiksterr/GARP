@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Installation de l'environnement Python (une seule fois, 2 a 3 minutes)...
if not exist .venv (
    python -m venv .venv || (echo Python 3.11+ introuvable : installez-le depuis python.org & pause & exit /b 1)
)
.venv\Scripts\python.exe -m pip install --upgrade pip -q
.venv\Scripts\python.exe -m pip install -r requirements.txt -q || (echo Echec de l'installation des dependances. & pause & exit /b 1)
echo.
echo Telechargement initial des donnees de marche (environ une heure)...
.venv\Scripts\python.exe -m pf maj
echo.
echo Termine. Lancez l'interface avec lancer.bat
pause
