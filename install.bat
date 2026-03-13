@echo off
echo Installing Juju FX EA Manager Dependencies...
echo ============================================

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed! Please install Python 3.8 or higher from python.org
    pause
    exit /b 1
)

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install required packages
echo Installing Flask and web frameworks...
pip install flask==2.3.3
pip install flask-cors==4.0.0
pip install flask-sock==0.7.0
pip install werkzeug==2.3.7

echo Installing database drivers...
pip install sqlite3-utils==1.8

echo Installing HTTP client libraries...
pip install requests==2.31.0

echo Installing utility libraries...
pip install python-dotenv==1.0.0

echo Creating requirements.txt for future use...
pip freeze > requirements.txt

echo ============================================
echo ✅ Installation Complete!
echo.
echo To run the application:
echo python app.py
echo.
pause