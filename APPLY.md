# Patch: spikeenc stub package

Fixes the `ModuleNotFoundError: No module named 'spikeenc'` collection error.

**Cause.** `src/` was an empty directory, and git does not track empty
directories, so it vanished on the first commit. setuptools then built an empty
distribution: `pip install` reported success, but there was no package. A
secondary problem was the failure *mode* — the tests import at module level, so
a missing package took down collection entirely instead of failing test by
test, which is the wrong signal for bottom-up work.

**Fix.** Ship the API surface as stubs. Every class and function from SPEC.md
now exists, with correct signatures and class attributes, and a body that
raises `NotImplementedError` naming the equations to implement.

`spiketrain.py` is implemented rather than stubbed. It is a data container
defined exactly by SPEC.md section 2, not research code, and having one
canonical implementation guarantees every encoder returns the same thing in the
same order.

## Apply

From the repository root:

    tar xzf spikeenc_stub_patch.tar.gz
    pip install -e ".[dev]"
    pytest -q

## Expected result

Collection succeeds. Roughly 45 tests fail with `NotImplementedError`, each
naming the equation it wants. Three should pass immediately, since they only
exercise `SpikeTrain`. That is the intended starting state.
