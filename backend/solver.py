"""Serialize HiGHS calls and use one native thread across ASGI worker threads."""
import threading
import warnings
from scipy.optimize import milp as scipy_milp

_lock = threading.Lock()

def milp(*args, **kwargs):
    options = {**kwargs.pop('options', {}), 'threads': 1}
    with _lock, warnings.catch_warnings():
        # SciPy forwards solver-specific options to HiGHS. The single-thread
        # option avoids shared native thread-pool lifecycle issues in TestClient/ASGI.
        warnings.filterwarnings('ignore', message='Unrecognized options detected.*', category=RuntimeWarning)
        return scipy_milp(*args, options=options, **kwargs)
