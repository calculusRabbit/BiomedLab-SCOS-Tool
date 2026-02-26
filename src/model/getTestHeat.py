import numpy as np
from scipy.ndimage import gaussian_filter

def getTestHeat(rows=50, cols=5, seed=None):
    if seed is not None:
        np.random.seed(seed)
    data = np.random.uniform(0, 1, (rows, cols))
    smooth = gaussian_filter(data, sigma=3)
    smooth = (smooth - smooth.min()) / (smooth.max() - smooth.min())
    return smooth.flatten().tolist()