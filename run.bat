@echo off
echo ===================================================
echo Starting CaptionForge Subtitle Generator
echo ===================================================

echo [1/2] Starting FastAPI Backend Server...
start "CaptionForge Backend" cmd /c "cd backend && ..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000"

echo [2/2] Starting Vite Frontend Server...
start "CaptionForge Frontend" cmd /c "cd frontend && npm run dev"

echo.
echo ===================================================
echo Servers are launching in separate windows!
echo - Frontend URL: http://localhost:5173
echo - Backend API:  http://127.0.0.1:8000
echo ===================================================
echo.
pause
