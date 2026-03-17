@echo off
chcp 65001 > nul

python -c "import fitz" 2>nul || pip install pymupdf

python "%~dp0usmle_server.py" --config "%~dp0config.txt"

pause
