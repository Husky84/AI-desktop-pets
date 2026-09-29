@echo off
rem ============================================================
rem  AI DeskPet launcher (Windows)
rem
rem  Kept deliberately simple, ASCII-only and label-free:
rem    * cmd.exe parses batch files with the system code page, so
rem      UTF-8 text can swallow the rest of the line. Localized
rem      messages live in tools\launch.py instead.
rem    * "call :label" misbehaves when the file has LF-only line
rem      endings (which git normalization can produce), so this
rem      file uses no labels at all.
rem  Everything smart - picking the Python that already has the
rem  dependencies, installing them if needed, starting the pet
rem  detached with pythonw - happens in tools\launch.py.
rem ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PY="

rem (a) the py launcher
where py >nul 2>nul && py -3 -c "import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul && set "PY=py -3"

rem (b) python / python3 from PATH, skipping Microsoft Store stubs
if not defined PY (
  for %%N in (python python3) do (
    if not defined PY (
      for /f "delims=" %%P in ('where %%N 2^>nul') do (
        if not defined PY (
          echo %%P | findstr /i "WindowsApps" >nul
          if errorlevel 1 (
            "%%P" -c "import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul
            if not errorlevel 1 set "PY=%%P"
          )
        )
      )
    )
  )
)

rem (c) common install locations (launch.py scans these too; this is a fallback)
if not defined PY (
  for %%D in (
    "%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "%ProgramData%\miniconda3\python.exe"
    "%ProgramData%\anaconda3\python.exe"
    "%USERPROFILE%\miniconda3\python.exe"
    "%USERPROFILE%\anaconda3\python.exe"
    "C:\Python314\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
  ) do (
    if not defined PY (
      if exist %%D (
        %%D -c "import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul
        if not errorlevel 1 set "PY=%%D"
      )
    )
  )
)

if not defined PY (
  echo.
  echo  [X] Python 3.10+ was not found.
  echo      Please install it from https://www.python.org/downloads/
  echo      and tick "Add python.exe to PATH" during setup.
  echo.
  pause
  exit /b 1
)

%PY% "%~dp0tools\launch.py"
if errorlevel 1 pause
exit /b 0
