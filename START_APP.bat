@echo off
echo ================================
echo  Invoice Extractor Launcher
echo ================================
echo.

REM Check if virtual environment exists
if not exist "venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found!
    echo Please run setup.bat first
    pause
    exit /b 1
)

REM Check if model exists
if not exist "app\models\mistral-7b.gguf" (
    echo ERROR: Model file not found!
    echo Please run setup.bat first to download the model
    pause
    exit /b 1
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Check if app.py exists
if not exist "app.py" (
    echo ERROR: app.py not found!
    echo Please ensure app.py is in the current directory
    pause
    exit /b 1
)

REM Launch the application
echo Starting Invoice Extractor...
echo.
python app.py

REM Keep window open if there's an error
if errorlevel 1 (
    echo.
    echo ================================
    echo  Application exited with error
    echo ================================
    pause
)