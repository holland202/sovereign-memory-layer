"""Comparison adapters. Defined and unit-checked, not comparatively evaluated.

Storage correctness and current-fact filtering are shared across all four arms.
Historical storage defects are not reintroduced into a scientific comparator.
"""
from .memory import METHODS, importance


def admit(store, method, key, value, *, provenance, governance=.5, entropy=1,
          residual=1, force_scar=False, thermal_state="NOMINAL", **kwargs):
    if method not in METHODS:
        raise ValueError("unknown method")
    if type(force_scar) is not bool:
        raise ValueError("force_scar must be boolean")
    if thermal_state != "NOMINAL" and thermal_state != "THROTTLE":
        if thermal_state == "SCAR_LOCK":
            return {"stored": False, "reason": "resource_gate"}
        raise ValueError("unknown resource state")
    w = importance(governance, entropy, residual)
    weighted = method in ("importance", "protected")
    if weighted and w < .30 and not (method == "protected" and force_scar):
        return {"stored": False, "reason": "formation_gate", "weight": w}
    protected = method == "protected" and (force_scar or (governance > .9 and entropy > 5))
    i = store.put(key, value, provenance=provenance, weight=w if weighted else 1,
                  protected=protected, thermal_state=thermal_state, **kwargs)
    return {"stored": True, "id": i, "weight": w if weighted else 1}
