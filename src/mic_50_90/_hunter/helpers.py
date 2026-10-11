from fractions import Fraction as F
import numpy as np

def _float(value,up):
    f=float(value)
    if (up and F(f)<value) or (not up and F(f)>value):
        f=float(np.nextafter(f,np.inf if up else -np.inf))
    return f


def _union_lower(calibration):
    """Independent union lower certificates, never upper p-value witnesses."""
    m=calibration.marginal_bounds
    values=[F(0),*[x.lower for x in m]]
    values += [m[i].lower+m[j].lower-pair.upper for (i,j),pair in calibration.pair_bounds.items()]
    values.append(sum(x.lower for x in m)-sum(x.upper for x in calibration.pair_bounds.values()))
    return max(values)

