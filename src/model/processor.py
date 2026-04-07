from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class SCOSResult:
    k2: float = 0.0
    bfi: float = 0.0
    cc: float = 0.0
    od: float = 0.0
    k2_images: tuple = (None, None, None, None, None, None)


def process_all_data(frame: np.ndarray) -> SCOSResult:
    return SCOSResult(
        k2 = compute_k2(frame),
        bfi = compute_bfi(frame),
        cc = compute_cc(frame),
        od = compute_od(frame),
        k2_images = (
            compute_k2_t1(frame),
            compute_k2_t2(frame),
            compute_k2_t3(frame),
            compute_k2_t4(frame),
            compute_k2_t5(frame),
            compute_k2_t6(frame),
        )
    )


# def compute_k2(Kf2):
#     # 
#     return mean(Kf2)

# def compute_bfi(Kf2):
#     return 1/mean(Kf2)

# def compute_cc(windowed_mean):
#     return windowed_mean

# def compute_od(windowed_mean):
#     OD = (-log10(abs(windowed_mean)./(ones(nTpts,1)*windowed_mean[0])));
#     return OD

# # FOR UPPER LEFT PANEL
# def img_windowed = reshapeWindow(img,window_size)
#     # this function will cut the img into small images, each small image size is window_size times window_size
#     img_width, img_height = get_img_size(img) # Vu please code this function to get width and length of img
#     n_width = floor(img_width/window_size) # calculate how many windows in horizontal x direction
#     n_height = floor(img_height/window_size) # calculate how many windows in vertical y direction
#     new_img_width = n_width*window_size;
#     new_img_height = n_height*window_size;
#     img = img[0:new_img_width-1; 0:new_img_height-1] # here crop the image so it can be divided into small windows

#     # calculate which pixels belong to which window
#     row_ind, col_ind = np.meshgrid(new_img_width, new_img_height)
#     window_ind_temp = ceil(row_ind./window_size) + (ceil(col_ind./window_size)-1)*n_height;
#     [~, window_ind] = sort(window_ind_temp(:))
#     img = reshape(img,[],1)
#     img = img(window_ind(:),:)
#     img_windowed = reshape(img,window_size*window_size,[])
#     return img_windowed

# def compute_k2_t1(frame: np.ndarray):
#     # This is K_raw_squared
#     # here the frame should be original frame minus average dark
#     window_size = 7
#     frame_windowed = reshapeWindow(frame,window_size)
#     windowed_mean = np.mean(frame_windowed,1)
#     windowed_var = np.var(frame_windowed,1)
#     K_raw_squared = windowed_var./windowed_mean
#     # here the size of K_raw_squared should be 7 times smaller than the frame
#     return (K_raw_squared)

# def compute_k2_t2(frame: np.ndarray):
#     # this is K_s_squared
#     gain = get_gain() # we should know what is the gain of the camera here
#     Ks2 = Gain./(windowed_mean);
#     return (Ks2)

# def compute_k2_t3(frame: np.ndarray):
#     # this is Kr2
#     window_size = 7
#     frame_windowed = reshapeWindow(frame,window_size)
#     windowed_mean = np.mean(frame_windowed,1)
#     dark_windowed = reshapeWindow(average_dark_img,window_size)
#     windowed_variance_dark = np.var(dark_windowed)
#     Kr2 = (mean(windowed_variance_dark) - 1/12)./((windowed_mean.^2));
#     return (Kr2)

# def compute_k2_t4(frame: np.ndarray, previous_frames):
#     # this is Ksp2
#     # here the previous_frames hold <50 previous frames right before the current frame; I don't want to hold too many frames in the memory
#     if length(previous_frames) < 50: # when we don't have 50 frames yet
#         Ksp2 = zeros(size(frame))
#     else:
#         window_size = 7
#         mean_50_frames = np.mean(previous_frames)
#         mean_50_frames_windowed = reshapeWindow(mean_50_frames,window_size)
#         spatial_variance = np.var(mean_50_frames_windowed,0,1);
#         spatial_mean = np.mean(mean_50_frames_windowed,1);
#         spatial_variance = spatial_variance - Gain*spatial_mean/50;
#         Ksp2 = spatial_variance./(spatial_mean.^2);
#     return (Ksp2)

# def compute_k2_t5(frame: np.ndarray):
#     # this is Kq2
#     window_size = 7
#     frame_windowed = reshapeWindow(frame,window_size)
#     windowed_mean = np.mean(frame_windowed,1)
#     Kq2 = 1/12./((windowed_mean.^2));
#     return (Kq2)

# def compute_k2_t6(frame: np.ndarray):
#     # I think we should have 6 windows right?
#     # we need all the previous images to calculate this one
#     Kf2 = Kraw2 - Ks2 - Kr2 - Kq2 - Ksp2
#     return (Kf2)


# def compute_od(frame: np.ndarray):
#     return frame.max()


# upper pannel:
def compute_k2_t1(frame):
    return frame

def compute_k2_t2(frame):
    return (frame * 0.8).astype(np.float32)

def compute_k2_t3(frame):
    return (frame * 0.6).astype(np.float32)

def compute_k2_t4(frame):
    return (frame * 0.4).astype(np.float32)

def compute_k2_t5(frame):
    return (frame * 0.2).astype(np.float32)

def compute_k2_t6(frame):
    return (frame * 0.1).astype(np.float32)
