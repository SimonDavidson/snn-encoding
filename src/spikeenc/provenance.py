"""Run provenance — configs in, results and manifest entries out.

Every reported number is written to `results/` as data and registered in
`results/manifest.json` with the script, config, commit hash and seed that
produced it (CLAUDE.md working practice; validation protocol section 6, and
the checklist item "commit hash, config and seed recorded in the results
manifest").

The point of the helper is that registering a result is one call and therefore
cannot be forgotten. A run that writes a data file without a manifest entry is
the failure this exists to prevent, so `record` does both or neither.

Configs are JSON rather than YAML: the environment has no yaml, JSON needs no
dependency, and it diffs cleanly in review, which matters because configs are
committed and are the thing Simon reviews before a sweep runs.

Author:        Simon Davidson & Claude
Created:       2026-09-05
Last modified: 2026-09-05
"""
import datetime as _dt
import json
import subprocess
from pathlib import Path

import numpy as np


class DirtyTreeError(RuntimeError):
    """Raised when a run is attempted with uncommitted tracked changes."""


def repo_root():
    """Top of the working tree."""
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True, check=True)
    return Path(out.stdout.strip())


def git_commit(allow_dirty=False):
    """Current commit hash, refusing to return one the tree does not match.

    "Commit hash at time of run" is only a provenance record if the tree was
    clean when the run happened; otherwise it names a state that never produced
    the numbers. Untracked files are ignored, since result files themselves are
    untracked at the moment they are written.
    """
    root = repo_root()
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        capture_output=True, text=True, check=True, cwd=root).stdout.strip()
    if dirty and not allow_dirty:
        raise DirtyTreeError(
            "refusing to record a result from a dirty tree — the commit hash "
            "would not describe the code that ran. Commit first, or pass "
            f"allow_dirty=True for an exploratory run.\n{dirty}")
    out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                         text=True, check=True, cwd=root)
    return out.stdout.strip() + ("-dirty" if dirty else "")


def assert_committed(*paths, allow_dirty=False):
    """Every path must be tracked and unmodified.

    The tree-level dirty check is not enough on its own: it ignores untracked
    files, so a brand-new script would record a result against a commit that
    does not contain the script that produced it. The run is reproducible from
    the repository only if the script and the config are both in the commit
    the manifest names.
    """
    if allow_dirty:
        return
    root = repo_root()
    for path in paths:
        rel = str(path)
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", rel],
                                 capture_output=True, text=True, cwd=root)
        if tracked.returncode != 0:
            raise DirtyTreeError(
                f"{rel} is not tracked by git, so the recorded commit hash "
                "would not contain it. Commit it before recording a result.")
        changed = subprocess.run(["git", "status", "--porcelain", "--", rel],
                                 capture_output=True, text=True, check=True,
                                 cwd=root).stdout.strip()
        if changed:
            raise DirtyTreeError(
                f"{rel} has uncommitted changes, so the recorded commit hash "
                "would not describe it. Commit it before recording a result.")


def load_config(path):
    """Read a committed run configuration. Every run is driven by one of these
    rather than by ad-hoc arguments, so that the run is reproducible from the
    repository alone."""
    path = Path(path)
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    cfg["_path"] = str(path)
    return cfg


def _jsonable(obj):
    """numpy scalars and arrays are not JSON-serialisable by default."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


def record(result_id, *, script, config, seed, values, arrays=None,
           predictions=None, results_dir=None, allow_dirty=False,
           supersede=False):
    """Write a result and register it, or do neither.

    `values` are the reported numbers, written as JSON to
    `results/<id>.json` and committed. `arrays` is optional bulk data, written
    to `results/<id>.npz`, which .gitignore excludes — large arrays stay local
    and the numbers that reach the paper stay in the repository.

    Re-running an id raises unless `supersede=True`, which appends the new
    entry and marks the old one superseded rather than editing it away. That is
    the convention DECISIONS.md already uses, applied to the manifest: a
    superseded record stays visible, so a reader can see that a number changed
    and when.
    """
    root = repo_root()
    results = Path(results_dir) if results_dir else root / "results"
    results.mkdir(parents=True, exist_ok=True)
    manifest_path = results / "manifest.json"
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)

    existing = [e for e in manifest["entries"]
                if e["id"] == result_id and not e.get("superseded_by")]
    if existing and not supersede:
        raise ValueError(
            f"{result_id!r} is already registered (run {existing[-1]['date']}, "
            f"commit {existing[-1]['commit'][:8]}). Use a new id, or pass "
            "supersede=True to record a replacement and mark the old entry "
            "superseded.")

    assert_committed(script, config, allow_dirty=allow_dirty)
    commit = git_commit(allow_dirty=allow_dirty)
    date = _dt.date.today().isoformat()

    out_json = results / f"{result_id}.json"
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(_jsonable(values), fh, indent=2, sort_keys=True)
        fh.write("\n")

    outputs = [str(out_json.relative_to(root))]
    if arrays:
        out_npz = results / f"{result_id}.npz"
        np.savez_compressed(out_npz, **arrays)
        outputs.append(str(out_npz.relative_to(root)))

    for e in existing:
        e["superseded_by"] = f"{result_id}@{date}"

    manifest["entries"].append({
        "id": result_id,
        "script": str(Path(script).relative_to(root)
                      if Path(script).is_absolute() else script),
        "config": str(config),
        "commit": commit,
        "seed": _jsonable(seed),
        "output": outputs if len(outputs) > 1 else outputs[0],
        "date": date,
        "predictions": predictions or [],
    })
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
    return out_json
