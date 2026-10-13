Each experiment lives in its own numbered folder under `experiments/`. This file explains how to start one, how runs are stored, and how to keep the index up to date.

## Starting a new experiment

1. Pick the next number from the index table below.
2. Copy the template and rename it:
    ``
   cp -r _templates/experiment experiments/004-short-name
   ```
3. Open `experiments/004-short-name/config.yaml` and update `experiment.name` and `experiment.description`.
4. Fill in the top of the experiment's `README.md` (question, what changed, status).
5. Put your real code in `train_and_eval` in `run.py`. Reusable pieces (data loading, models, metrics, plotting) belong in `shared/`, not in the experiment folder.
6. Add a row to the index table in this file.
7. Open a PR with the branch named after the folder, for example `exp/004-short-name`.

## Folder layout

```
experiments/
├── README.md                this file, plus the index
└── 004-short-name/
    ├── README.md            question, changes, rerun command, conclusion
    ├── config.yaml          base config for this experiment
    ├── run.py               entry point
    ├── scripts/             any other scripts specific to this experiment
    └── results/
        ├── 2026-10-13_01/
        │   ├── config.yaml      exact merged config that ran
        │   ├── run_info.json    git commit, seed, command, python version
        │   ├── metrics.json     output of train_and_eval
        │   └── figures/         plots, tables, anything else produced
        └── 2026-10-13_02/
```

Folder names are a number plus a short slug. Run folders are `YYYY-MM-DD_NN`, where `NN` restarts at 01 each day. `run.py` creates run folders itself, so never make one by hand.

## Running an experiment

From inside the experiment folder:

```
python run.py
python run.py --config config.yaml
python run.py --set train.lr=0.0003 --set seed=7
```

- `--set key=value` overrides any config value for that run only. Nested keys use dots, such as `train.lr`. You can repeat the flag.
- The merged config is saved into the run folder before training starts, so a crashed run still leaves a record.
- Edit `config.yaml` itself only when you want to change the defaults for future runs.

## Reproducibility rules

- Commit before any run you care about. `run_info.json` records a `dirty` flag, and if it is true, the commit hash alone will not reproduce that run.
- Always set a seed in the config.
- Keep large files (checkpoints, raw logs, big datasets) out of git. Store them in a bucket or tracker and link to them in the experiment README.
- Small summary files like `metrics.json` and a few figures are fine to commit.

## Writing the experiment README

Keep it short. Each experiment README should have:

- **Status:** active, done, or archived
- **Question:** what you are trying to find out
- **What changed:** the difference from the previous experiment
- **How to rerun:** the exact command
- **Conclusion:** what happened, including when it failed

Failed experiments are worth keeping and documenting, since they stop the next person from repeating them.

## Archiving an experiment

Do not move or delete the folder. Instead:

1. Change `Status` in the experiment's README to `archived`.
2. Add the date and a one-line reason at the top of that README.
3. Update the status in the index table below.

Leaving it in place keeps numbers and links stable.

## Index

Update this table in the same PR that adds or changes an experiment.

| ID  | Name          | Status | Question                    | Key result | PR |
|-----|---------------|--------|-----------------------------|------------|----|
| 001 | baseline      | done   | What is baseline accuracy?  |            |    |
| 002 | lr-sweep      | active | Does a lower LR help?       |            |    |
