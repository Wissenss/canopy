call ./.venv/Scripts/activate

pyinstaller --onefile --collect-submodules=demucs --add-data "%~dp0models;models" --specpath "./build" --name "canopy" main.py
