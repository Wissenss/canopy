call ./.venv/Scripts/activate

rem build timestamp shown in the cli banner
python -c "import datetime; open(r'%~dp0build_info.py', 'w').write('BUILD_TIME = \'' + datetime.datetime.now().strftime('%%Y-%%m-%%d %%H:%%M:%%S') + '\'\n')"

rem pyinstaller only rebuilds the exe when the icon path changes, not its content; removing the exe forces the final step
if exist "%~dp0dist\canopy.exe" del "%~dp0dist\canopy.exe"

pyinstaller --onefile --collect-submodules=demucs --add-data "%~dp0models;models" --icon "%~dp0canopy.ico" --specpath "./build" --name "canopy" main.py
