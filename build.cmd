call ./.venv/Scripts/activate

rem build timestamp shown in the cli banner
python -c "import datetime; open(r'%~dp0build_info.py', 'w').write('BUILD_TIME = \'' + datetime.datetime.now().strftime('%%Y-%%m-%%d %%H:%%M:%%S') + '\'\n')"

rem pyinstaller only rebuilds the exe when the icon path changes, not its content; removing the exe forces the final step
if exist "%~dp0dist\canopy.exe" del "%~dp0dist\canopy.exe"

pyinstaller --onefile --collect-submodules=demucs --add-data "%~dp0models;models" --icon "%~dp0canopy.ico" --specpath "./build" --name "canopy" main.py

if not exist "%~dp0dist\canopy.exe" exit /b 1

rem release package: dist\canopy_<version>_x64.7z with the exe, license and readme
python -c "import sys, os, py7zr; sys.path.insert(0, r'%~dp0.'); from version import __version__; z = py7zr.SevenZipFile(os.path.join(r'%~dp0dist', f'canopy_{__version__}_x64.7z'), 'w'); [z.write(os.path.join(r'%~dp0.', p), os.path.basename(p)) for p in (r'dist\canopy.exe', 'license', 'readme.md')]; z.close()"
