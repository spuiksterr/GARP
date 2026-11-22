@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Environnement absent : lancez d'abord installer.bat
    pause
    exit /b 1
)
echo Interface disponible sur http://localhost:8501  (fermez cette fenetre pour l'arreter)
start "" /min cmd /c "timeout /t 6 >nul & start http://localhost:8501"
.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501 --server.address localhost
