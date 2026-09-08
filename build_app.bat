@echo off
echo ============================================
echo   Building ARIA (fast-start version)
echo ============================================
py -m pip install -r requirements.txt --quiet
py -m pip install pyinstaller --quiet
echo.
echo   Packaging (this can take a minute or two)...
py -m PyInstaller --onedir --windowed --name ARIA ^
  --add-data "aria_ui.html;." ^
  --collect-all edge_tts ^
  --hidden-import=playsound ^
  aria_webview.py
echo.
echo ============================================
echo   Done! Your app folder is at: dist\ARIA
echo   The program to run is: dist\ARIA\ARIA.exe
echo.
echo   Why a folder instead of one file?
echo   A single-file .exe has to unzip itself into
echo   a temp folder EVERY time you open it, which
echo   is what was making startup slow. This folder
echo   version extracts once (right now) so ARIA.exe
echo   opens fast every time after.
echo.
echo   To make it feel like a single app: right-click
echo   dist\ARIA\ARIA.exe -^> "Send to" -^> "Desktop
echo   (create shortcut)". Then just use that shortcut
echo   icon - you'll never need to open the folder.
echo ============================================
pause
