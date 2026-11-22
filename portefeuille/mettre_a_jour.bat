@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Mise a jour des cours, fondamentaux (> 7 jours) et scores. Peut etre planifiee
rem dans le Planificateur de taches Windows (par exemple chaque samedi matin).
.venv\Scripts\python.exe -m pf maj
.venv\Scripts\python.exe -m pf export
