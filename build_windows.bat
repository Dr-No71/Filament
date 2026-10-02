@echo off
python -m pip install --upgrade pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed --name FilamentManager filament_manager.py
echo.
echo Fertig. Die EXE liegt im Ordner dist.
pause
