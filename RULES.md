epo Rules

This file explains how we work in this repo: where things go, how we use branches and PRs, how experiments are run, and what the automated checks do. If something here stops making sense, change it with a PR so the rules stay honest.

The goal is simple. Anyone on the team should be able to find any result, see exactly how it was produced, and rerun it.

## 1. Repo layout

```
repo/
├── README.md              what this project is and how to get started
├── RULES.md               this file
├── .gitignore
├── shared/                code used by more than one experiment
├── experiments/           one numbered folder per experiment (see section 4)
│   └── README.md          guide and index of all experiments
├── _templates/
│   └── experiment/        copy this to start a new experiment
├── docs/                  methods notes, decisions, writeups
├── paper/                 drafts, if we write in the repo
└── .github/
    ├── workflows/
    └── pull_request_template.md
```

Where things go:

- **Reusable code** goes in `shared/`. If two experiments need the same loader, model, or metric, it lives there and both import it.
- **Experiment-specific code** stays in that experiment's folder.
- **Notebooks** are for exploring. If a notebook produces something we rely on, move the logic into `shared/` or an experiment script and call it from there. Notebooks never get imported by anything.
- **Data** is not stored in git. See section 6.

## 2. Branches

Branch names loosely follow the following naming conventions. Most branches will have an owner name who created the branch and whether it is a general feature or experiment and its name as follows. 
| Branch | Purpose |
|--------|---------|
| `main` | Always works, always reproducible. Protected. Changes only come in through PRs. |
| `<owner-name>/feature/<short-name>` | New shared code, tooling, or analysis. Example: `aran/feature/f1-metric` |
| `<owner-name>/exp/<NNN-short-name>` | One experiment. The name matches the folder. Example: `aran/exp/004-longer-context` |

Rules:

- Branch from `main` and keep branches short lived.
- Do your best not to directly commit to main.
- One PR adds or changes one experiment or one feature. Do not bundle several experiments into one PR.
- If an experiment fails or gets abandoned, still merge a short README that explains the dead end, also moving the folder into the `archived/` folder. Deleting the branch with nothing written down wastes the work.
- Tag milestones and paper submissions (`v0.1-workshop`, `v1.0-submission`) so we can return to the exact state behind a result(command is git tag v0.1-submission). This command assigns a tag to a commit that we can reference later. 

## 3. Pull requests

- Keep PRs small and focused.
- We squash-merge, so `main` has one clean commit per PR.
- Fill in the PR template. 


```
## What changed
One or two sentences.

## Why
The question or problem this addresses.

## How to check it
Commands to run, expected output, config used.

## Results (if relevant)
Key numbers, plots, or a link to the run. Note seed and data version.

## Checklist
- [ ] Tests pass
- [ ] Config and seed recorded
- [ ] Docs or README updated if needed
- [ ] Experiment index updated (if this adds or changes an experiment)
- [ ] No large files or secrets committed
```

## 4. Experiments

Each experiment is a numbered folder under `experiments/`. The full guide is in `experiments/README.md`. The short version:

```
experiments/004-short-name/
├── README.md        status, question, what changed, rerun command, conclusion
├── config.yaml      base config
├── run.py           entry point
├── scripts/         other scripts specific to this experiment
└── results/
    └── 2026-10-13_01/
        ├── config.yaml      exact merged config that ran
        ├── run_info.json    git commit, seed, command, python version
        ├── metrics.json
        └── figures/
```

To start one:

1. Copy `_templates/experiment` to `experiments/NNN-short-name`, using the next free number.
2. Update the config name and description, and fill in the top of the experiment README.
3. Write the experiment in `run.py`, with shared pieces in `shared/`.
4. Add a row to the index in `experiments/README.md`.
5. Open a PR from `exp/NNN-short-name`.

To run one, go into its folder and use `python run.py`. Use `--set key=value` for one-off changes, for example `python run.py --set train.lr=0.0003`. Run folders are created by `run.py` and named `YYYY-MM-DD_NN`. Never create them by hand.

**Archiving.** Do not move or delete an old experiment. Set its status to `archived` in its README with the date and a one-line reason, and update the status in the index. That keeps numbers and links stable.

## 5. Reproducibility

- Every run must set a seed in its config.
- Commit before any run you care about. `run_info.json` records whether the working tree was dirty, and a dirty run cannot be reproduced from the commit hash alone.
- Dependencies are pinned. If you add a package, update the environment file in the same PR.
- Each experiment README states the command needed to rerun it.
- Report results from saved run folders, not from memory or from a notebook that has since been edited.

## 6. Data and large files

- `data/raw/` is read-only by convention. Never edit raw data by hand. Cleaning happens in code and writes to `interim/` or `processed/`.
- Large files (datasets, checkpoints, raw logs) stay out of git. Use DVC, Git LFS, or a bucket, and document how to get them in the README or a download script.
- Small summary files (`metrics.json`, a few figures) are fine to commit.
- Never commit secrets, API keys, or `.env` files. If one slips in, rotate the key. Deleting the commit is not enough.

## 7. Quick checklist before opening a PR

- [ ] Branch name follows the convention above
- [ ] Code runs from a clean checkout using the pinned environment
- [ ] Config and seed are recorded
- [ ] Experiment README and index are updated
- [ ] No data, checkpoints, or secrets are in the diff
- [ ] PR template is filled in

## 8. Changing these rules

Open a PR that edits this file and explain why. Rules that nobody follows should be fixed or removed, not ignored.
