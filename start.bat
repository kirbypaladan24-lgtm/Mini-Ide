@echo off
setlocal

echo.
echo  ^<^< Mini IDE ^>^>  Phase 1 startup
echo  ----------------------------------------
echo.

echo  [1/2]  Backend  ^(FastAPI ^+ Uvicorn^)
echo         http://localhost:8000
echo.
start "Mini IDE — Backend" cmd /k "cd /d "%~dp0backend" && pip install -r ..\requirements.txt -q && uvicorn main:app --reload --port 8000"

:: Give the backend a moment before opening the browser
timeout /t 2 /nobreak > nul

echo  [2/2]  Frontend ^(React ^+ Vite^)
echo         http://localhost:5173
echo.
start "Mini IDE — Frontend" cmd /k "cd /d "%~dp0frontend" && npm install && npm run dev"

echo  ----------------------------------------
echo  Open http://localhost:5173 in your browser.
echo  Both windows must stay open while using the IDE.
echo.
pause
