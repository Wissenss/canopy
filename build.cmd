call ./.venv/Scripts/activate

pyinstaller --onefile --collect-submodules=webrtcvad --specpath "./build" --name "canopy" main.py