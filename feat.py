import librosa
import torch
import numpy as np
import pandas as pd
from demucs.pretrained import get_model
from demucs.apply import apply_model

device = "cuda" if torch.cuda.is_available() else "cpu"
model = get_model("htdemucs")
vocals_idx = model.sources.index("vocals")

def get_vocals_start_end(file_path : str, analisis_window : int = 60, min_vocals_amplitud : float = 1):
    """
        returns the second when the voice starts / end in the given audio file.

        parms:
            analisis_window : int = 60 seconds -> this functions checks the first and last <analisis_window> seconds
    """
    
    v_s = 0
    v_f = 0

    # load the wave form data
    y, sr = librosa.load(path=file_path, sr=model.samplerate, mono=False, offset=0, duration=analisis_window)

    wav = torch.tensor(y, dtype=torch.float32)
    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8

    # extract vocals track
    with torch.no_grad():
        src = apply_model(model, ((wav - mean) / std)[None].to(device), device=device, split=True, progress=False)[0]

    vocals = (src[vocals_idx] * std + mean).mean(0).cpu().numpy()

    #hop = int(sr * FRAME_MS / 1000)

    # check if there is any speaking at all...

    v_db = librosa.amplitude_to_db(librosa.feature.rms(y=vocals)[0] + 1e-9)

    if v_db < 1:
        return 0, 0

    # get the first / last spoken segment
    
    

    return v_s, v_f    

if __name__ == "__main__":
    file_path = "./other/MUS00030.mp3"

    v_s, v_e = get_vocals_start_end(file_path, 60)

    print(f"v_s: {v_s}, v_e: {v_e}")
