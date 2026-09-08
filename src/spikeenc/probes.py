"""Probes — the decoders of proposal section 6.2.

Only the linear probe is here. The nonlinear probe is a two-layer bidirectional
GRU, which needs a tensor library this environment does not have and cannot be
written responsibly against a CPU-only box without first knowing the cost; it
is deferred, with the accessibility gap of equation (33) left unmeasured until
it exists.

**Why this is written out rather than taken from scikit-learn.** Not
preference. The CI workflow installs `.[dev]` — numpy, scipy, pytest — and runs
every test file in `tests/`, and the workflow is a design-session file the
implementation session may not edit. A probe requiring scikit-learn would make
its own tests unrunnable in the one environment that checks them independently.
The implementation below is checked against scikit-learn out of tree instead,
and the agreement recorded in NOTEBOOK.md; that gets the third-party validation
without the dependency.

Fairness constraint C4 requires identical decoding across encoders — "same
optimiser, schedule, regularisation and stopping criterion". Those live in
`LinearProbe.__init__` and nowhere else, and every fitted probe reports them in
`.settings`, so what a result was obtained under travels with the result.

Author:        Simon Davidson & Claude
Created:       2026-09-07
Last modified: 2026-09-07
"""
import numpy as np
from scipy.linalg import solve
from scipy.optimize import minimize
from scipy.special import logsumexp

from .tasks import UNLABELLED


class LinearProbe:
    """Multinomial logistic regression, L2-regularised, fitted by L-BFGS-B.

    Deterministic: the objective is convex, the initial point is the origin,
    and L-BFGS-B is deterministic, so a fit depends on the data alone. There
    is no seed because there is nothing for one to control — which is worth
    stating, since C8 asks for three seeds per condition and for this probe the
    seed enters only through the corpus and the split.
    """

    def __init__(self, n_classes, alpha=1e-4, max_iter=500, tol=1e-8,
                 standardise=True):
        self.n_classes = int(n_classes)
        self.alpha = float(alpha)          # L2 penalty, on weights not biases
        self.max_iter = int(max_iter)
        self.tol = float(tol)
        self.standardise = bool(standardise)
        self.W = None
        self.b = None
        self._mu = None
        self._sigma = None
        self._keep = None
        self.n_iter_ = None
        self.converged_ = None

    @property
    def settings(self):
        """What C4 requires to be identical across encoders, in one place."""
        return {"probe": "linear_multinomial_logreg", "alpha": self.alpha,
                "max_iter": self.max_iter, "tol": self.tol,
                "standardise": self.standardise, "optimiser": "L-BFGS-B",
                "n_classes": self.n_classes}

    # -- internals ---------------------------------------------------------

    def _prepare(self, x, fit):
        x = np.asarray(x, dtype=np.float64)
        if not self.standardise:
            return x
        if fit:
            self._mu = x.mean(axis=0)
            sigma = x.std(axis=0)
            # A feature with no variance over the training set carries no
            # information, and is *dropped* rather than rescaled. Mapping its
            # sigma to 1.0 leaves an all-zero column, which makes X'X exactly
            # singular — and for a unipolar encoder that is not an edge case:
            # `featurise` leaves the whole OFF half at zero by design, so half
            # of every E1 feature vector is constant and cond(X'X) is infinite
            # at every operating point.
            self._keep = sigma > 0.0
            self._sigma = sigma[self._keep]
        return (x[:, self._keep] - self._mu[self._keep]) / self._sigma

    def _objective(self, theta, x, onehot, n_features):
        w = theta[:n_features * self.n_classes].reshape(n_features,
                                                        self.n_classes)
        bias = theta[n_features * self.n_classes:]
        z = x @ w + bias
        # log softmax via logsumexp: exp(z) overflows for large logits, and the
        # probe is fitted on standardised features whose logits are not bounded
        # a priori.
        log_p = z - logsumexp(z, axis=1, keepdims=True)
        n = x.shape[0]
        loss = -np.sum(log_p * onehot) / n + 0.5 * self.alpha * np.sum(w * w)

        resid = (np.exp(log_p) - onehot) / n
        grad_w = x.T @ resid + self.alpha * w
        grad_b = resid.sum(axis=0)
        return loss, np.concatenate([grad_w.ravel(), grad_b])

    # -- interface ---------------------------------------------------------

    def fit(self, x, y):
        """Fit on the labelled frames of `(x, y)`; UNLABELLED rows are dropped."""
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.int64)
        keep = y != UNLABELLED
        x, y = x[keep], y[keep]
        if x.shape[0] == 0:
            raise ValueError("no labelled frames to fit on")
        if y.min() < 0 or y.max() >= self.n_classes:
            raise ValueError(f"labels outside [0, {self.n_classes})")

        x = self._prepare(x, fit=True)
        n_features = x.shape[1]
        onehot = np.zeros((x.shape[0], self.n_classes))
        onehot[np.arange(x.shape[0]), y] = 1.0

        theta0 = np.zeros(n_features * self.n_classes + self.n_classes)
        res = minimize(self._objective, theta0, args=(x, onehot, n_features),
                       method="L-BFGS-B", jac=True,
                       options={"maxiter": self.max_iter, "ftol": self.tol,
                                "gtol": self.tol})
        self.W = res.x[:n_features * self.n_classes].reshape(n_features,
                                                             self.n_classes)
        self.b = res.x[n_features * self.n_classes:]
        self.n_iter_ = int(res.nit)
        self.converged_ = bool(res.success)
        return self

    def decision_function(self, x):
        if self.W is None:
            raise RuntimeError("probe is not fitted")
        return self._prepare(x, fit=False) @ self.W + self.b

    def predict(self, x):
        return np.argmax(self.decision_function(x), axis=1)

    def predict_proba(self, x):
        """Class posteriors. T3 picks peaks in a boundary posterior, so it needs
        a calibrated-ish score rather than a hard decision; the softmax of the
        logits is what multinomial logistic regression is fitted to produce."""
        z = self.decision_function(x)
        z = z - z.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(axis=1, keepdims=True)

    def score(self, x, y):
        """Frame-level accuracy over labelled frames."""
        y = np.asarray(y, dtype=np.int64)
        keep = y != UNLABELLED
        if not np.any(keep):
            return float("nan")
        return float(np.mean(self.predict(np.asarray(x)[keep]) == y[keep]))

    def confusion(self, x, y):
        """Counts, true labels on rows — the input to equation (38)."""
        y = np.asarray(y, dtype=np.int64)
        keep = y != UNLABELLED
        y_true = y[keep]
        y_pred = self.predict(np.asarray(x)[keep])
        k = self.n_classes
        flat = np.bincount(y_true * k + y_pred, minlength=k * k)
        return flat.reshape(k, k)


class RidgeProbe:
    """L2-regularised linear regression — the T2 decoder of proposal 6.2.

    Closed form rather than iterative: the normal equations are solved
    directly, so there is no optimiser, no stopping criterion and no seed, and
    two fits on identical data are bit-identical without anything having to be
    arranged.

    Targets are regressed in the space the metric is reported in. Proposal 4.2
    reports RMSE in semitones and gives the reason — the perceptual scale is
    logarithmic, and 10 Hz means something different at 100 Hz and at 300 Hz.
    Fitting in hertz and converting afterwards would minimise squared *hertz*
    error, weighting high-f0 frames more heavily than the metric does; fitting
    in semitones makes estimator and metric agree (Q33). The caller passes
    semitones; this class only records what it was given.
    """

    def __init__(self, alpha=1.0, standardise=True, target_space="semitones"):
        self.alpha = float(alpha)
        self.standardise = bool(standardise)
        self.target_space = target_space
        self.w = None
        self.intercept = None
        self._mu = None
        self._sigma = None
        self._keep = None

    @property
    def settings(self):
        return {"probe": "ridge", "alpha": self.alpha,
                "standardise": self.standardise, "solver": "normal_equations",
                "target_space": self.target_space}

    def _prepare(self, x, fit):
        x = np.asarray(x, dtype=np.float64)
        if not self.standardise:
            return x
        if fit:
            self._mu = x.mean(axis=0)
            sigma = x.std(axis=0)
            # Dropped, not rescaled — see LinearProbe._prepare. Ridge felt this
            # far more sharply than the logistic probe: the zero columns make
            # the Gram matrix singular, and with alpha small against a diagonal
            # of order n the informative-but-collinear directions are then
            # under-regularised enough to produce predictions off by hundreds
            # of octaves.
            self._keep = sigma > 0.0
            self._sigma = sigma[self._keep]
        return (x[:, self._keep] - self._mu[self._keep]) / self._sigma

    def fit(self, x, y):
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        # Checked before standardising, not after: computing a mean over zero
        # rows emits RuntimeWarnings and produces NaNs, so a guard placed after
        # it raises the right error having already made a mess on the way.
        if x.shape[0] == 0:
            raise ValueError("no frames to fit on")
        if x.shape[0] != y.shape[0]:
            raise ValueError(f"{x.shape[0]} rows against {y.shape[0]} targets")
        x = self._prepare(x, fit=True)
        # The intercept is the target mean rather than a penalised coefficient:
        # penalising it would shrink the prediction towards zero semitones,
        # which is 100 Hz and not a neutral point.
        self.intercept = float(y.mean())
        gram = x.T @ x + self.alpha * np.eye(x.shape[1])
        self.w = solve(gram, x.T @ (y - self.intercept), assume_a="pos")
        return self

    def predict(self, x):
        if self.w is None:
            raise RuntimeError("probe is not fitted")
        return self._prepare(x, fit=False) @ self.w + self.intercept
