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
            # A feature constant over the training set carries no information
            # and would divide by zero. Left at unit scale, which maps it to a
            # constant column the intercept absorbs.
            self._sigma = np.where(sigma > 0.0, sigma, 1.0)
        return (x - self._mu) / self._sigma

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
