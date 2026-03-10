import numpy as np
from model.scos_result import SCOSResult
def process_all_data(frame):
    k2 = compute_k2(frame)
    bfi = compute_bfi(frame)
    cc = compute_cc(frame)
    od = compute_od(frame)





    return SCOSResult(
            frame=frame,
            k2=k2,
            bfi=bfi,
            cc=cc,
            od=od,
        )





# function
def compute_k2(frame):
    return frame.mean()


def compute_bfi(frame):
    return frame.mean() / 255.0 + np.random.uniform(-0.05, 0.05)

def compute_cc(frame):
    return frame.std()

def compute_od(frame):
    return frame.max()