@echo off
echo ================================
echo  Invoice Extractor Setup
echo ================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ and try again
    pause
    exit /b 1
)

REM Create virtual environment
echo [1/4] Creating virtual environment...
if not exist "venv" (
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
    echo Virtual environment created successfully
) else (
    echo Virtual environment already exists, skipping...
)
echo.

REM Activate virtual environment
echo [2/4] Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment
    pause
    exit /b 1
)
echo.

REM Install requirements
echo [3/4] Installing requirements...
if exist "requirements.txt" (
    pip install --upgrade pip
    pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install requirements
        pause
        exit /b 1
    )
    echo Requirements installed successfully
) else (
    echo WARNING: requirements.txt not found, skipping...
)
echo.

REM Create models directory
if not exist "app\models" (
    mkdir app\models
    echo Created models directory
)

REM Download model
echo [4/4] Downloading Mistral-7B model...
echo This may take several minutes (file size ~4GB)...
echo.

set MODEL_URL=https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf?download=true
set MODEL_FILE=app\models\mistral-7b.gguf

if exist "%MODEL_FILE%" (
    echo Model already exists at %MODEL_FILE%
    echo Skipping download...
) else (
    echo Downloading to %MODEL_FILE%...
    
    REM Try curl first (Windows 10+)
    curl --version >nul 2>&1
    if not errorlevel 1 (
        curl -L --insecure -o "%MODEL_FILE%" "%MODEL_URL%"
        if errorlevel 1 (
            echo ERROR: Download failed with curl
            goto TRY_POWERSHELL
        )
        goto DOWNLOAD_SUCCESS
    )
    
    :TRY_POWERSHELL
    REM Fallback to PowerShell
    echo curl not found, trying PowerShell...
    powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; [System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true}; (New-Object System.Net.WebClient).DownloadFile('%MODEL_URL%', '%MODEL_FILE%')}"
    if errorlevel 1 (
        echo ERROR: Download failed with PowerShell
        echo.
        echo Please manually download the model from:
        echo %MODEL_URL%
        echo.
        echo Save it as: %MODEL_FILE%
        pause
        exit /b 1
    )
    
    :DOWNLOAD_SUCCESS
    echo Model downloaded successfully!
)

echo.
echo ================================
echo  Setup Complete!
echo ================================
echo.
echo To run the application, use: run.bat
echo.
pause