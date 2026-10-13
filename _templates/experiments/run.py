
"""
Entry point for this experiment.

Usage:
    python run.py
    python run.py --config config.yaml
    python run.py --set train.lr=0.0003 --set seed=7

Each call creates results/YYYY-MM-DD_NN/ containing:
    config.yaml    the final merged config that actually ran
    run_info.json  git commit, seed, timestamp, python version
    metrics.json   whatever train_and_eval returns
"""

import argparse
import copy
import json
import platform
import random
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

# Make code in shared/ importable: experiments/<name>/run.py -> repo root is two levels up.
EXP_DIR = Path(__file__).resolve().parent
REPO_ROOT = EXP_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT))


# ---------- config handling ----------

def load_config(path):
    with open(path) as f:
        return yaml.safe_load(f)


def apply_overrides(cfg, overrides):
    """Apply overrides like 'train.lr=0.0003' to a nested dict."""
    cfg = copy.deepcopy(cfg)
    for item in overrides:
        if "=" not in item:
            raise ValueError(f"Override must look like key=value, got: {item}")
        key, raw = item.split("=", 1)
        value = yaml.safe_load(raw)  # turns "0.01" into a float, "true" into a bool
        node = cfg
        parts = key.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return cfg


# ---------- run bookkeeping ----------

def make_run_dir(results_root):
    """Create results/YYYY-MM-DD_NN, where NN restarts at 01 each day."""
    results_root.mkdir(exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    existing = [p.name for p in results_root.glob(f"{today}_*") if p.is_dir()]
    nums = [int(n.split("_")[1]) for n in existing if n.split("_")[1].isdigit()]
    run_dir = results_root / f"{today}_{max(nums, default=0) + 1:02d}"
    run_dir.mkdir()
    return run_dir


def git_info():
    def run(*args):
        return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()
    try:
        return {
            "commit": run("rev-parse", "HEAD"),
            "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(run("status", "--porcelain")),
        }
    except Exception:
        return {"commit": None, "branch": None, "dirty": None}


def set_seed(seed):
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError:
        pass
    try:
        import torch
        torch.manual_seed(seed)
    except ImportError:
        pass


# ---------- your experiment goes here ----------

def train_and_eval(cfg, run_dir):
    """Replace this with real code. Put reusable pieces in shared/ and import them.

    Return a dict of metrics. Save any figures or checkpoints into run_dir.
    """
    # from shared.data import load_dataset
    # from shared.models import build_model
    print(f"Training with lr={cfg['train']['lr']} for {cfg['train']['epochs']} epochs")
    return {"val_loss": None, "val_metric": None}


# ---------- main ----------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(EXP_DIR / "config.yaml"))
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                        help="override a config value, e.g. --set train.lr=0.0003")
    args = parser.parse_args()

    cfg = apply_overrides(load_config(args.config), args.set)
    run_dir = make_run_dir(EXP_DIR / "results")

    # Save what is about to run before running it, so crashed runs are still traceable.
    with open(run_dir / "config.yaml", "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)

    info = {
        "started": datetime.now().isoformat(timespec="seconds"),
        "seed": cfg.get("seed"),
        "command": " ".join(sys.argv),
        "python": platform.python_version(),
        "git": git_info(),
    }
    with open(run_dir / "run_info.json", "w") as f:
        json.dump(info, f, indent=2)

    set_seed(cfg.get("seed", 0))
    metrics = train_and_eval(cfg, run_dir)

    with open(run_dir / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"Done. Results in {run_dir}")


if __name__ == "__main__":
    main()
