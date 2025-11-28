@echo off

REM Change to the directory where this script is located
cd /d "%~dp0"

echo ================================
echo  Invoice Extractor Setup
echo ================================
echo.

REM Check if Python is installed (and not just the Microsoft Store stub)
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from the Company Portal and try again
    pause
    exit /b 1
)

REM Check if this is the Microsoft Store stub (it outputs nothing meaningful)
python -c "print('OK')" >nul 2>&1
if errorlevel 1 (
    echo.
    echo ================================
    echo  Microsoft Store Python Detected
    echo ================================
    echo The Microsoft Store version of Python may not work properly.
    echo.
    echo Please install Python from: https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation
    echo.
    pause
    exit /b 1
)

REM Detect Microsoft Store Python by checking the path
for /f "tokens=*" %%i in ('python -c "import sys; print(sys.executable)"') do set PYTHON_PATH=%%i
echo Python found at: %PYTHON_PATH%
echo.

REM Detect Python version
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo Python version: %PYTHON_VERSION%

REM Extract major.minor version (e.g., 3.13 -> MAJOR=3, MINOR=13)
for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VERSION%") do (
    set MAJOR=%%a
    set MINOR=%%b
)
echo Detected: Python %MAJOR%.%MINOR%
echo.

echo %PYTHON_PATH% | findstr /i "WindowsApps" >nul
if not errorlevel 1 (
    echo.
    echo ================================
    echo  WARNING: Microsoft Store Python
    echo ================================
    echo You are using Python from the Microsoft Store.
    echo This may cause issues with virtual environments.
    echo.
    echo RECOMMENDED: Install Python from python.org instead
    echo Download: https://www.python.org/downloads/
    echo.
    set /p CONTINUE="Continue anyway? (y/N): "
    if /i not "%CONTINUE%"=="y" (
        echo Setup cancelled
        pause
        exit /b 1
    )
    echo.
    echo Attempting setup with Store Python...
    echo.
)

REM Create virtual environment
echo [1/5] Creating virtual environment...
if not exist "venv" (
    python -m venv venv --without-pip
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        echo.
        echo If using Microsoft Store Python, please:
        echo 1. Uninstall Microsoft Store Python
        echo 2. Install from https://www.python.org/downloads/
        echo 3. Check "Add Python to PATH" during installation
        pause
        exit /b 1
    )
    
    REM For Store Python, manually install pip
    echo Installing pip in virtual environment...
    call venv\Scripts\activate.bat
    python -m ensurepip --default-pip >nul 2>&1
    if errorlevel 1 (
        echo Downloading get-pip.py...
        powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile 'get-pip.py'}"
        python get-pip.py
        del get-pip.py
    )
    
    echo Virtual environment created successfully
) else (
    echo Virtual environment already exists, skipping...
)
echo.

REM Activate virtual environment
echo [2/5] Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment
    pause
    exit /b 1
)
echo.

REM Verify pip is available
pip --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: pip is not available in the virtual environment
    echo Try deleting the 'venv' folder and running setup.bat again
    pause
    exit /b 1
)

REM Upgrade pip first
echo [3/5] Upgrading pip...
pip install --upgrade pip
echo.

REM Install llama-cpp-python with PREBUILT CPU wheel (NO COMPILATION NEEDED)
echo [4/5] Installing llama-cpp-python (CPU version)
echo This will download a prebuilt wheel - no compilation required!
echo.

REM Try the official CPU wheel repository first
echo Attempting to install prebuilt CPU wheel
pip install llama-cpp-python --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

if errorlevel 1 (
    echo.
    echo First attempt failed, trying alternative community wheels
    
    REM Try jllllll's community CPU wheels (these are very reliable)
    pip install llama-cpp-python --prefer-binary --extra-index-url https://jllllll.github.io/llama-cpp-python-cuBLAS-wheels/AVX2/cpu
    
    if errorlevel 1 (
        echo.
        echo Trying basic CPU wheels (no AVX2)
        pip install llama-cpp-python --prefer-binary --extra-index-url https://jllllll.github.io/llama-cpp-python-cuBLAS-wheels/basic/cpu
        
        if errorlevel 1 (
            echo.
            echo All prebuilt wheel sources failed.
            echo Trying direct PyPI installation
            pip install llama-cpp-python --prefer-binary
            
            if errorlevel 1 (
                echo.
                echo ================================
                echo  INSTALLATION FAILED
                echo ================================
                echo.
                echo Could not install prebuilt llama-cpp-python wheels.
                echo This usually means:
                echo  1. Your Python version is not supported by prebuilt wheels
                echo  2. Network/firewall is blocking the download
                echo  3. No wheels exist for your system configuration
                echo.
                echo Python Version: %PYTHON_VERSION%
                echo.
                echo NEXT STEPS:
                echo  1. Try using Python 3.11 or 3.12 (best wheel support)
                echo  2. Check your internet connection and firewall
                echo  3. Contact IT support with this error message
                echo.
                pause
                exit /b 1
            )
        )
    )
)

echo.
echo llama-cpp-python installed successfully!
echo.

REM Install remaining requirements
echo [5/5] Installing remaining requirements...
if exist "requirements.txt" (
    REM Install everything except llama-cpp-python (already handled)
    findstr /v /i "llama-cpp-python" requirements.txt > requirements_temp.txt
    pip install -r requirements_temp.txt
    if errorlevel 1 (
        echo ERROR: Failed to install requirements
        del requirements_temp.txt
        pause
        exit /b 1
    )
    del requirements_temp.txt
    echo Requirements installed successfully
) else (
            echo WARNING: requirements.txt not found, skipping
)
echo.

REM Create models directory
if not exist "app\models" (
    mkdir app\models
    echo Created models directory
)

REM Download model
echo [6/6] Downloading Mistral-7B model
echo This may take several minutes (file size ~4GB)
echo.

set MODEL_URL=https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf?download=true
set MODEL_FILE=app\models\mistral-7b.gguf

if exist "%MODEL_FILE%" (
    echo Model already exists at %MODEL_FILE%
    echo Skipping download...
) else (
    echo Downloading to %MODEL_FILE%
    
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
    echo curl not found, trying PowerShell
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
echo Installed with CPU-only acceleration (no GPU required)
echo This is perfect for most invoice extraction tasks.
echo.
echo To run the application, use: START_APP.bat
echo.
pause