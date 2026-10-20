"""
LSTM regression from NinaPro EMG to hand kinematics (CyberGlove joint angles).

Input:  sliding windows of EMG, shape (window, n_emg_channels)
Target: glove readings at the last sample of each window, shape (n_glove_channels,)

Rest samples (movement label 0) are removed before windowing. Removing them
leaves gaps in the recording, so the signal is first cut into contiguous
movement segments and windows are only drawn from inside a segment. A window
never spans two movements.

Train/val/test are split by repetition (each movement is repeated several times
per subject), so test windows come from repetitions the model never saw.

Run through run.py, which calls train_and_eval with the merged config.yaml:
    python run.py
    python run.py --set data.subjects=[1,2,3] --set data.exercises=[1]
    python run.py --set data.downsample=20  # DB2 (2 kHz raw EMG)

Expects NinaPro .mat files (e.g. S1_A1_E1.mat) anywhere under data.path. Each
file must contain `emg`, `glove`, and `restimulus`/`stimulus` plus
`rerepetition`/`repetition`.
"""

import re
from pathlib import Path

import numpy as np
import scipy.io
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

EXP_DIR = Path(__file__).resolve().parent

FILE_RE = re.compile(r"S(\d+)_.*E(\d+)", re.IGNORECASE)


# ---------- data loading ----------

def find_mat_files(data_dir, subjects, exercises):
    files = []
    for path in sorted(Path(data_dir).rglob("*.mat")):
        m = FILE_RE.search(path.stem)
        if not m:
            continue
        subject, exercise = int(m.group(1)), int(m.group(2))
        if subjects and subject not in subjects:
            continue
        if exercises and exercise not in exercises:
            continue
        files.append((subject, exercise, path))
    if not files:
        raise FileNotFoundError(
            f"No NinaPro .mat files matching subjects={subjects} exercises={exercises} "
            f"under {data_dir}. Run shared/download_ninapro.py and unzip any per-subject archives."
        )
    return files


def _pick(mat, *keys):
    for k in keys:
        if k in mat:
            return np.asarray(mat[k])
    raise KeyError(f"None of {keys} found in .mat file (keys: {sorted(k for k in mat if not k.startswith('__'))})")


def load_recording(path, downsample):
    """Return emg (T, C_emg), glove (T, C_glove), label (T,), repetition (T,)."""
    mat = scipy.io.loadmat(path)
    emg = _pick(mat, "emg").astype(np.float32)
    glove = _pick(mat, "glove").astype(np.float32)
    # restimulus/rerepetition are the relabeled versions aligned to actual movement onset.
    label = _pick(mat, "restimulus", "stimulus").ravel().astype(np.int64)
    rep = _pick(mat, "rerepetition", "repetition").ravel().astype(np.int64)

    n = min(len(emg), len(glove), len(label), len(rep))
    emg, glove, label, rep = emg[:n], glove[:n], label[:n], rep[:n]

    if downsample > 1:
        # Rectify and average over non-overlapping blocks: a crude EMG envelope at the lower rate.
        n_blocks = n // downsample
        cut = n_blocks * downsample
        emg = np.abs(emg[:cut]).reshape(n_blocks, downsample, -1).mean(axis=1)
        glove = glove[:cut].reshape(n_blocks, downsample, -1).mean(axis=1)
        label = label[:cut:downsample]
        rep = rep[:cut:downsample]

    return emg, glove, label, rep


def split_into_movement_segments(emg, glove, label, rep):
    """Drop rest (label 0) and return contiguous runs of one movement/repetition."""
    active = label != 0
    # A new segment starts wherever activity, label, or repetition changes.
    change = np.ones(len(label), dtype=bool)
    change[1:] = (active[1:] != active[:-1]) | (label[1:] != label[:-1]) | (rep[1:] != rep[:-1])
    starts = np.flatnonzero(change)
    ends = np.append(starts[1:], len(label))

    segments = []
    for s, e in zip(starts, ends):
        if not active[s]:
            continue
        segments.append({
            "emg": emg[s:e],
            "glove": glove[s:e],
            "label": int(label[s]),
            "rep": int(rep[s]),
        })
    return segments


def load_segments(files, downsample):
    segments = []
    n_total, n_rest = 0, 0
    for subject, exercise, path in files:
        emg, glove, label, rep = load_recording(path, downsample)
        n_total += len(label)
        n_rest += int((label == 0).sum())
        for seg in split_into_movement_segments(emg, glove, label, rep):
            seg["subject"] = subject
            seg["exercise"] = exercise
            segments.append(seg)
    print(f"Loaded {len(files)} files: {n_total} samples, removed {n_rest} rest samples "
          f"({100 * n_rest / max(n_total, 1):.1f}%), kept {len(segments)} movement segments")
    return segments


# ---------- normalization ----------

class Standardizer:
    def __init__(self, segments, key):
        x = np.concatenate([s[key] for s in segments], axis=0)
        self.mean = x.mean(axis=0)
        self.std = x.std(axis=0)
        self.std[self.std < 1e-8] = 1.0  # dead or constant channels

    def transform(self, x):
        return (x - self.mean) / self.std

    def inverse(self, x):
        return x * self.std + self.mean


def normalize_segments(segments, emg_norm, glove_norm):
    return [
        {**s, "emg": emg_norm.transform(s["emg"]).astype(np.float32),
              "glove": glove_norm.transform(s["glove"]).astype(np.float32)}
        for s in segments
    ]


# ---------- dataset ----------

class WindowDataset(Dataset):
    """Windows are indexed lazily as (segment, end) pairs instead of being copied out."""

    def __init__(self, segments, window, stride):
        self.segments = segments
        self.window = window
        self.index = []
        for i, seg in enumerate(segments):
            for end in range(window, len(seg["emg"]) + 1, stride):
                self.index.append((i, end))

    def __len__(self):
        return len(self.index)

    def __getitem__(self, idx):
        i, end = self.index[idx]
        seg = self.segments[i]
        x = seg["emg"][end - self.window:end]
        y = seg["glove"][end - 1]
        return torch.from_numpy(x), torch.from_numpy(y)


# ---------- model ----------

class LSTMRegressor(nn.Module):
    def __init__(self, n_in, n_out, hidden_size, num_layers, dropout, bidirectional):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=n_in,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
            bidirectional=bidirectional,
        )
        out_dim = hidden_size * (2 if bidirectional else 1)
        self.head = nn.Sequential(
            nn.LayerNorm(out_dim),
            nn.Dropout(dropout),
            nn.Linear(out_dim, n_out),
        )

    def forward(self, x):
        out, _ = self.lstm(x)        # (B, T, H)
        return self.head(out[:, -1])  # predict kinematics at the last time step


# ---------- training / evaluation ----------

def pick_device(name):
    if name != "auto":
        return torch.device(name)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def run_epoch(model, loader, loss_fn, device, optimizer=None, grad_clip=None):
    training = optimizer is not None
    model.train(training)
    total, count = 0.0, 0
    with torch.set_grad_enabled(training):
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            pred = model(x)
            loss = loss_fn(pred, y)
            if training:
                optimizer.zero_grad()
                loss.backward()
                if grad_clip:
                    nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
                optimizer.step()
            total += loss.item() * len(x)
            count += len(x)
    return total / max(count, 1)


@torch.no_grad()
def predict(model, loader, device):
    model.eval()
    preds, targets = [], []
    for x, y in loader:
        preds.append(model(x.to(device)).cpu().numpy())
        targets.append(y.numpy())
    return np.concatenate(preds), np.concatenate(targets)


def regression_metrics(pred, target):
    """Per-channel and mean RMSE, R², and Pearson r. Inputs are in original glove units."""
    err = pred - target
    rmse = np.sqrt((err ** 2).mean(axis=0))
    ss_res = (err ** 2).sum(axis=0)
    ss_tot = ((target - target.mean(axis=0)) ** 2).sum(axis=0)
    r2 = 1 - ss_res / np.where(ss_tot > 0, ss_tot, np.nan)

    pc = pred - pred.mean(axis=0)
    tc = target - target.mean(axis=0)
    denom = np.sqrt((pc ** 2).sum(axis=0) * (tc ** 2).sum(axis=0))
    r = (pc * tc).sum(axis=0) / np.where(denom > 0, denom, np.nan)

    return {
        "rmse_mean": float(np.nanmean(rmse)),
        "r2_mean": float(np.nanmean(r2)),
        "pearson_mean": float(np.nanmean(r)),
        "rmse_per_channel": rmse.tolist(),
        "r2_per_channel": [None if np.isnan(v) else float(v) for v in r2],
        "pearson_per_channel": [None if np.isnan(v) else float(v) for v in r],
    }


# ---------- entry point (called by run.py) ----------

def train_and_eval(cfg, run_dir):
    """Train on the config from run.py, save best_model.pt into run_dir, return metrics."""
    data_cfg, model_cfg, train_cfg = cfg["data"], cfg["model"], cfg["train"]
    device = pick_device(train_cfg.get("device", "auto"))

    data_dir = (EXP_DIR / data_cfg["path"]).resolve()
    files = find_mat_files(data_dir, data_cfg.get("subjects"), data_cfg.get("exercises"))
    segments = load_segments(files, data_cfg.get("downsample", 1))

    val_reps, test_reps = data_cfg["val_reps"], data_cfg["test_reps"]
    held_out = set(val_reps) | set(test_reps)
    train_segs = [s for s in segments if s["rep"] not in held_out]
    val_segs = [s for s in segments if s["rep"] in val_reps]
    test_segs = [s for s in segments if s["rep"] in test_reps]
    del segments  # the splits hold the only references needed from here on
    if not (train_segs and val_segs and test_segs):
        raise ValueError(f"Empty split: train={len(train_segs)} val={len(val_segs)} test={len(test_segs)} segments. "
                         f"Check data.val_reps/data.test_reps against the repetitions in the data.")

    # Fit normalization on training data only.
    emg_norm = Standardizer(train_segs, "emg")
    glove_norm = Standardizer(train_segs, "glove")
    train_segs, val_segs, test_segs = (normalize_segments(s, emg_norm, glove_norm)
                                       for s in (train_segs, val_segs, test_segs))

    window = data_cfg["window"]
    train_ds = WindowDataset(train_segs, window, data_cfg.get("stride", 1))
    val_ds = WindowDataset(val_segs, window, data_cfg.get("eval_stride", 1))
    test_ds = WindowDataset(test_segs, window, data_cfg.get("eval_stride", 1))
    print(f"Windows: train={len(train_ds)} val={len(val_ds)} test={len(test_ds)}")

    loader_kw = dict(batch_size=train_cfg["batch_size"], num_workers=train_cfg.get("num_workers", 0))
    train_dl = DataLoader(train_ds, shuffle=True, drop_last=True, **loader_kw)
    val_dl = DataLoader(val_ds, shuffle=False, **loader_kw)
    test_dl = DataLoader(test_ds, shuffle=False, **loader_kw)

    n_emg = train_segs[0]["emg"].shape[1]
    n_glove = train_segs[0]["glove"].shape[1]
    model = LSTMRegressor(n_emg, n_glove, model_cfg["hidden_size"], model_cfg["num_layers"],
                          model_cfg["dropout"], model_cfg.get("bidirectional", False)).to(device)
    print(f"Model: {n_emg} EMG channels -> {n_glove} glove channels, "
          f"{sum(p.numel() for p in model.parameters()):,} params, device={device}")

    optimizer = torch.optim.AdamW(model.parameters(), lr=train_cfg["lr"],
                                  weight_decay=train_cfg.get("weight_decay", 0.0))
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, factor=0.5, patience=2)
    loss_fn = nn.MSELoss()
    checkpoint = Path(run_dir) / "best_model.pt"

    best_val, best_epoch, bad_epochs = float("inf"), -1, 0
    history = []
    for epoch in range(1, train_cfg["epochs"] + 1):
        train_loss = run_epoch(model, train_dl, loss_fn, device, optimizer, train_cfg.get("grad_clip"))
        val_loss = run_epoch(model, val_dl, loss_fn, device)
        scheduler.step(val_loss)
        history.append({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss})
        print(f"epoch {epoch:3d}  train {train_loss:.4f}  val {val_loss:.4f}  "
              f"lr {optimizer.param_groups[0]['lr']:.1e}")

        if val_loss < best_val:
            best_val, best_epoch, bad_epochs = val_loss, epoch, 0
            torch.save(model.state_dict(), checkpoint)
        else:
            bad_epochs += 1
            if bad_epochs >= train_cfg.get("patience", train_cfg["epochs"]):
                print(f"Early stopping at epoch {epoch}")
                break

    model.load_state_dict(torch.load(checkpoint, map_location=device))
    pred, target = predict(model, test_dl, device)
    test_metrics = regression_metrics(glove_norm.inverse(pred), glove_norm.inverse(target))
    print(f"Test: RMSE {test_metrics['rmse_mean']:.3f}  R² {test_metrics['r2_mean']:.3f}  "
          f"r {test_metrics['pearson_mean']:.3f}")

    return {
        "val_loss": best_val,  # normalized MSE at the best epoch
        "val_metric": None,
        "best_epoch": best_epoch,
        "device": str(device),
        "test": test_metrics,
        "history": history,
        "files": [str(p) for _, _, p in files],
    }
