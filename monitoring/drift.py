"""Compare les distributions récentes à une référence fixe."""
import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, ks_2samp


def psi(reference, current):
    ref = pd.to_numeric(pd.Series(reference), errors="raise").dropna().to_numpy()
    cur = pd.to_numeric(pd.Series(current), errors="raise").dropna().to_numpy()
    if not len(ref) or not len(cur):
        return None
    distinct = np.unique(ref)
    if len(distinct) == 1:
        width = max(abs(distinct[0]) * 1e-6, 1e-6)
        middle = np.array([distinct[0] - width, distinct[0] + width])
    elif len(distinct) <= 20:
        middle = distinct[:-1] + np.diff(distinct) / 2
    else:
        middle = np.unique(np.quantile(ref, np.linspace(0, 1, 11)))[1:-1]
    edges = np.r_[-np.inf, middle, np.inf]
    p = np.histogram(ref, edges)[0].astype(float) + 1e-6
    q = np.histogram(cur, edges)[0].astype(float) + 1e-6
    p, q = p / p.sum(), q / q.sum()
    return float(np.sum((q - p) * np.log(q / p)))


def compare(reference, current, numeric, categorical):
    report = []
    for feature in numeric:
        ref, cur = reference[feature].dropna(), current[feature].dropna()
        value = psi(ref, cur)
        report.append({"feature": feature, "psi": value,
                       "ks_pvalue": float(ks_2samp(ref, cur).pvalue) if len(ref) and len(cur) else None,
                       "status": "no_data" if value is None else "investigate" if value > .25 else "watch" if value > .10 else "stable",
                       "out_of_reference_range": float(((cur < ref.min()) | (cur > ref.max())).mean()) if len(cur) and len(ref) else None})
    for feature in categorical:
        ref, cur = reference[feature].dropna(), current[feature].dropna()
        categories = ref.value_counts().index.union(cur.value_counts().index)
        table = np.array([ref.value_counts().reindex(categories, fill_value=0), cur.value_counts().reindex(categories, fill_value=0)])
        pvalue = None
        if len(ref) and len(cur) and len(categories) > 1:
            _, p, _, expected = chi2_contingency(table)
            if (expected >= 5).all():
                pvalue = float(p)
        report.append({"feature": feature, "chi2_pvalue": pvalue,
                       "reference_frequencies": {str(k): float(v) for k, v in ref.value_counts(normalize=True).items()},
                       "current_frequencies": {str(k): float(v) for k, v in cur.value_counts(normalize=True).items()},
                       "unknown_rate": float((cur == "unknown").mean()) if len(cur) else None,
                       "status": "investigate" if pvalue is not None and pvalue < .05 else "stable" if pvalue is not None else "insufficient_counts"})
    return report


def outside_reference(reference, current, numeric):
    """Indique, client par client, si une variable numérique sort des valeurs observées dans la référence."""
    outside = pd.Series(False, index=current.index)
    for feature in numeric:
        outside |= (current[feature] < reference[feature].min()) | (current[feature] > reference[feature].max())
    return outside
