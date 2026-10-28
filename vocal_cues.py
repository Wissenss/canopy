import sys
import yaml
import librosa
import torch
import numpy as np
from pathlib import Path
from demucs.pretrained import get_model
from demucs.apply import apply_model, BagOfModels
from demucs.hf import load_safetensors_model

MODEL_NAME = "htdemucs"

def _load_model():
    """
        loads the demucs model from the bundled ./models folder (or the pyinstaller temp folder), falling back to the HF hub download.
    """

    model_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "models" / MODEL_NAME
    if not model_dir.is_dir():
        return get_model(MODEL_NAME)

    with open(model_dir / f"{MODEL_NAME}.yaml") as file:
        bag = yaml.safe_load(file)

    models = [load_safetensors_model(model_dir / f"{sig}.safetensors") for sig in bag["models"]]
    bag_model = BagOfModels(models, bag.get("weights"), bag.get("segment"))
    bag_model.eval()
    return bag_model

device = "cuda" if torch.cuda.is_available() else "cpu"
model = _load_model()
model.to(device)
vocals_idx = model.sources.index("vocals")

HOP_LENGTH = 512

def _get_vocals_db(file_path: str, offset: float, duration: float):
    """
        returns the vocals RMS (dB) per frame for the given segment of the audio file.
    """

    # load the wave form data
    y, sr = librosa.load(path=file_path, sr=model.samplerate, mono=False, offset=offset, duration=duration)

    # demucs expects stereo
    if y.ndim == 1:
        y = np.stack([y, y])

    wav = torch.tensor(y, dtype=torch.float32)
    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8

    # extract vocals track
    with torch.no_grad():
        src = apply_model(model, ((wav - mean) / std)[None].to(device), device=device, split=True, progress=False)[0]

    vocals = (src[vocals_idx] * std + mean).mean(0).cpu().numpy()

    return librosa.amplitude_to_db(librosa.feature.rms(y=vocals, hop_length=HOP_LENGTH)[0] + 1e-9), sr

def get_vocal_cues(file_path: str, analisis_window: int = 60, min_vocals_db: float = -40):
    """
        returns the second when the voice starts / end in the given audio file.

        parms:
            analisis_window : int = 60 seconds -> this functions checks the first and last <analisis_window> seconds
            min_vocals_db : float = -40 dBFS -> frames of the vocals track above this level are considered voice
    """

    total = librosa.get_duration(path=file_path)

    # get the first spoken segment
    v_db, sr = _get_vocals_db(file_path, 0, analisis_window)
    voiced = np.flatnonzero(v_db > min_vocals_db)

    # check if there is any speaking at all...
    if voiced.size == 0:
        return 0, 0

    v_s = float(librosa.frames_to_time(voiced[0], sr=sr, hop_length=HOP_LENGTH))

    # get the last spoken segment (reuse the first window if the file is short)
    offset = 0.0
    if total > analisis_window:
        offset = total - analisis_window
        v_db, sr = _get_vocals_db(file_path, offset, analisis_window)
        voiced = np.flatnonzero(v_db > min_vocals_db)

    v_f = total
    if voiced.size > 0:
        v_f = min(total, offset + float(librosa.frames_to_time(voiced[-1] + 1, sr=sr, hop_length=HOP_LENGTH)))

    return v_s, v_f

if __name__ == "__main__":
    file_path = "./other/MUS00040.mp3"

    v_s, v_e = get_vocal_cues(file_path, 60)

    print(f"v_s: {v_s}, v_e: {v_e}")
