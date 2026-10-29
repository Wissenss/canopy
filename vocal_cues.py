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

def _sustained_segments(voiced: np.ndarray, sr: int, min_sustain: float, min_sustain_interval: float) -> list[tuple[int, int]]:
    """
        returns the (first, last) frame of each voiced segment lasting at least min_sustain seconds.

        voiced frames separated by gaps up to min_sustain_interval seconds belong to the same segment (0 -> only continuous vocals).
    """

    idx = np.flatnonzero(voiced)
    if idx.size == 0:
        return []

    frame_s = HOP_LENGTH / sr
    max_gap = int(min_sustain_interval / frame_s)

    # a new segment starts where the distance to the previous voiced frame is bigger than the tolerated gap
    breaks = np.flatnonzero(np.diff(idx) > max_gap + 1)
    starts = np.concatenate(([idx[0]], idx[breaks + 1]))
    ends = np.concatenate((idx[breaks], [idx[-1]]))

    return [(int(s), int(e)) for s, e in zip(starts, ends) if (e - s + 1) * frame_s >= min_sustain]

def get_vocal_cues(file_path: str, analisis_window: int = 60, min_vocals_db: float | None = -18, min_relative_db: float | None = None,
                   min_sustain: float = 0, min_sustain_interval: float = 0):
    """
        returns the second when the voice starts / end in the given audio file.

        parms:
            analisis_window : int = 60 seconds -> this functions checks the first and last <analisis_window> seconds
            min_vocals_db : float = -18 dBFS -> frames of the vocals track above this level are considered voice, None -> not used
            min_relative_db : float = None dB -> frames of the vocals track up to this many dB below its peak are considered voice, None -> not used
                              (the peak is taken from both analyzed windows; when used along min_vocals_db a frame must pass both)
            min_sustain : float = 0 seconds -> vocals must last at least this long to count as the start / end
            min_sustain_interval : float = 0 seconds -> gaps between vocals up to this long still count for min_sustain, 0 -> continuous vocals
    """

    total = librosa.get_duration(path=file_path)

    start_db, sr = _get_vocals_db(file_path, 0, analisis_window)

    # min_relative_db only makes thresholds stricter, so without any frame above min_vocals_db there are no vocals at all
    if min_vocals_db is not None and not np.any(start_db > min_vocals_db):
        return 0, 0

    # last window (reuse the first one if the file is short)
    offset = 0.0
    end_db = start_db
    if total > analisis_window:
        offset = total - analisis_window
        end_db, sr = _get_vocals_db(file_path, offset, analisis_window)

    threshold = -np.inf
    if min_vocals_db is not None:
        threshold = min_vocals_db
    if min_relative_db is not None:
        threshold = max(threshold, max(start_db.max(), end_db.max()) - min_relative_db)

    # get the first sustained vocals segment
    start_segments = _sustained_segments(start_db > threshold, sr, min_sustain, min_sustain_interval)

    # check if there is any speaking at all...
    if not start_segments:
        return 0, 0

    v_s = float(librosa.frames_to_time(start_segments[0][0], sr=sr, hop_length=HOP_LENGTH))

    # get the last sustained vocals segment
    end_segments = _sustained_segments(end_db > threshold, sr, min_sustain, min_sustain_interval)

    v_f = total
    if end_segments:
        v_f = min(total, offset + float(librosa.frames_to_time(end_segments[-1][1] + 1, sr=sr, hop_length=HOP_LENGTH)))

    return v_s, v_f

if __name__ == "__main__":
    file_path = "./other/MUS00040.mp3"

    v_s, v_e = get_vocal_cues(file_path, 60)

    print(f"v_s: {v_s}, v_e: {v_e}")
