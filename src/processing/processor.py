from collections import deque
import numpy as np
from processing.scos_result import SCOSResult

WINDOW_SIZE = 7  # default window size (pixels)
GAIN = 0.3755 # default gain use this for all computation

def process_all_data(frame: np.ndarray, gain: float, exposure_time: float, dark_image: np.ndarray | None, frame_buf: deque) -> SCOSResult:
    if dark_image is not None:
        frame = frame - dark_image #i assume we use frame - avg dark image for every function need frame
    frame_windowed = reshape_window(frame, WINDOW_SIZE)
    windowed_mean = np.mean(frame_windowed, axis=0)
    print("Windowed_mean", windowed_mean[-21:], "\n") 

    k_raw2 = compute_k_raw2(frame_windowed, windowed_mean)
    k_s2 = compute_k_s2(windowed_mean, gain)
    k_r2 = compute_k_r2(windowed_mean, dark_image)
    k_sp2 = compute_k_sp2(frame, frame_buf, gain)
    k_q2 = compute_k_q2(windowed_mean)
    k_f2 = compute_k_f2(k_raw2, k_s2, k_r2, k_sp2, k_q2)

    return SCOSResult(
        k2 = compute_k2(k_f2),
        bfi = compute_bfi(k_f2),
        cc = compute_cc(windowed_mean),
        od = compute_od(windowed_mean),
        k2_images = (k_raw2, k_s2, k_r2, k_sp2, k_q2, k_f2),
    )


# spatial windowing

def reshape_window(img: np.ndarray, window_size: int) -> np.ndarray:

    # REFERENCE (original dr. gao matlab's code):
        # this function will cut the img into small images, each small image size is window_size times window_size
        # img_width, img_height = get_img_size(img) # Vu please code this function to get width and length of img
        # n_width = floor(img_width/window_size) # calculate how many windows in horizontal x direction
        # n_height = floor(img_height/window_size) # calculate how many windows in vertical y direction
        # new_img_width = n_width*window_size;
        # new_img_height = n_height*window_size;
        # img = img[0:new_img_width-1; 0:new_img_height-1] # here crop the image so it can be divided into small windows

        # # calculate which pixels belong to which window
        # row_ind, col_ind = np.meshgrid(new_img_width, new_img_height)
        # window_ind_temp = ceil(row_ind./window_size) + (ceil(col_ind./window_size)-1)*n_height;
        # [~, window_ind] = sort(window_ind_temp(:))
        # img = reshape(img,[],1)
        # img = img(window_ind(:),:)
        # img_windowed = reshape(img,window_size*window_size,[])
        # return img_windowed

    h, w = img.shape
    nw = w // window_size
    nh = h // window_size
    # crop so dimensions are exact multiples of window_size
    img = img[:nh * window_size, :nw * window_size].astype(np.float64)
    # reshape into patches: (nh, window_size, nw, window_size)
    img = img.reshape(nh, window_size, nw, window_size)
    # transpose to (nh, nw, window_size, window_size) then flatten patches
    img = img.transpose(0, 2, 1, 3).reshape(nh * nw, window_size * window_size)
    return img.T   # (window_size^2, n_windows) — column = one window


# May be needed later to reshape windowed output back to 2D spatial map (nh, nw) for display.
# def window_output_shape(img: np.ndarray, window_size: int):
#     # Return (nh, nw) the spatial dimensions of the windowed output map
#     return img.shape[0] // window_size, img.shape[1] // window_size


## K^2 component functions ##
def compute_k_raw2(frame_windowed, windowed_mean) -> np.ndarray:

    # MATLAB reference:
    #     # This is K_raw_squared
    #     # here the frame should be original frame minus average dark
    #     window_size = 7
    #     frame_windowed = reshapeWindow(frame,window_size)
    #     windowed_mean = np.mean(frame_windowed,1)
    #     windowed_var = np.var(frame_windowed,1)
    #     K_raw_squared = windowed_var./windowed_mean
    #     # here the size of K_raw_squared should be 7 times smaller than the frame
    #     return (K_raw_squared)

    windowed_var = np.var(frame_windowed, axis=0)
    K_raw_squared = windowed_var / windowed_mean

    return K_raw_squared


def compute_k_s2(windowed_mean, gain: float) -> np.ndarray | None:
    # MATLAB REFERENCE:
        # this is K_s_squared
        # gain = get_gain() # we should know what is the gain of the camera here
        # Ks2 = Gain./(windowed_mean);
        # return (Ks2)
    
    Ks2 = GAIN / windowed_mean
    return Ks2


def compute_k_r2(windowed_mean, dark_image: np.ndarray | None) -> np.ndarray | None:
    # MATLAB REFERENCE:
        # this is Kr2
        #     window_size = 7
        #     frame_windowed = reshapeWindow(frame,window_size)
        #     windowed_mean = np.mean(frame_windowed,1)
        #     dark_windowed = reshapeWindow(average_dark_img,window_size)
        #     windowed_variance_dark = np.var(dark_windowed)
        #     Kr2 = (mean(windowed_variance_dark) - 1/12)./((windowed_mean.^2))

    if dark_image is None:
        print("Dark image is None at function compute Kr2")
        return np.zeros_like(windowed_mean)
    
    dark_windowed = reshape_window(dark_image, WINDOW_SIZE)
    windowed_variance_dark = np.var(dark_windowed, axis=0) # per window varriance
    Kr2 = (np.mean(windowed_variance_dark) - 1/12) / np.square(windowed_mean)
    
    return Kr2


def compute_k_sp2(frame: np.ndarray, frame_buf: deque, gain: float) -> np.ndarray | None:
    # MATLAB REFERENCE:
    # # this is Ksp2
    # # here the previous_frames hold <50 previous frames right before the current frame; I don't want to hold too many frames in the memory
    # if length(previous_frames) < 50: # when we don't have 50 frames yet
    #     Ksp2 = zeros(size(frame))
    # else:
    #     window_size = 7
    #     mean_50_frames = np.mean(previous_frames)
    #     mean_50_frames_windowed = reshapeWindow(mean_50_frames,window_size)
    #     spatial_variance = np.var(mean_50_frames_windowed,0,1);
    #     spatial_mean = np.mean(mean_50_frames_windowed,1);
    #     spatial_variance = spatial_variance - Gain*spatial_mean/50;
    #     Ksp2 = spatial_variance./(spatial_mean.^2);
    # return (Ksp2)

    # in pipeline i already set frame buf = 50 size which contain 50 images
    if len(frame_buf) < 50:
        n_windows = (frame.shape[0] // WINDOW_SIZE) * (frame.shape[1] // WINDOW_SIZE)
        return np.zeros(n_windows)

    frames_50 = np.array(list(frame_buf)) #(50, H, W)

    mean_50_frames = np.mean(frames_50, axis=0)
    mean_50_frames_windowed = reshape_window(mean_50_frames, WINDOW_SIZE) 

    spatial_variance = np.var(mean_50_frames_windowed, axis=0)
    spatial_mean = np.mean(mean_50_frames_windowed, axis=0)
    spatial_variance = spatial_variance - (GAIN * spatial_mean) / 50

    Ksp2 = spatial_variance / np.square(spatial_mean)

    return Ksp2


def compute_k_q2(windowed_mean) -> np.ndarray | None:
    # MATLAB REFERENCE:
    # # this is Kq2
    # window_size = 7
    # frame_windowed = reshapeWindow(frame,window_size)
    # windowed_mean = np.mean(frame_windowed,1)
    # Kq2 = 1/12./((windowed_mean.^2));
    # return (Kq2)

    Kq2 = (1/12) / np.square(windowed_mean)
    
    return Kq2


def compute_k_f2(
    k_raw2: np.ndarray | None,
    k_s2: np.ndarray | None,
    k_r2: np.ndarray | None,
    k_sp2: np.ndarray | None,
    k_q2: np.ndarray | None,
) -> np.ndarray | None:

    # MATLAB REFERENCE:
    # Kf2 = Kraw2 - Ks2 - Kr2 - Kq2 - Ksp2
    # return (Kf2)

    Kf2 = k_raw2 - k_s2 - k_r2 - k_sp2 - k_q2
    return Kf2



## 4 plots on the right panel ##
def compute_k2(k_f2: np.ndarray | None) -> float:
    # MATLAB REFERENCE:
    # k2 = mean(Kf2)
    if k_f2 is None:
        print("k_f2 is none")
        return 0.0
    
    k2 = float(np.mean(k_f2))
    return k2


def compute_bfi(k_f2: np.ndarray | None) -> float:
    # MATLAB REFERENCE:
    # BFI = 1 / mean(Kf2)
    if k_f2 is None or np.mean(k_f2) == 0: #zero divsion check
        print("k_f2 is none or mean is 0")
        return 0.0
    BFI = float(1 / np.mean(k_f2))
    return BFI


def compute_cc(windowed_mean) -> float:
    # MATLAB REFERENCE:
    # cc = windowed_mean

    return float(np.mean(windowed_mean))


def compute_od(windowed_mean) -> float:
    # MATLAB REFERENCE:
    # OD = -log10(abs(windowed_mean) ./ (ones(nTpts,1) * windowed_mean(1)))
    return 0.0  # TODO: needs windowed_mean_initial from first frame
