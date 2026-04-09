import cv2
import numpy as np
dark_img = cv2.imread("average_image.png", cv2.IMREAD_GRAYSCALE)
dark_img = dark_img.astype(np.float128)
print(np.all(dark_img == 0))

non_zero_values = dark_img[dark_img != 0]
print(dark_img.shape)
print(non_zero_values)
coords = np.argwhere(dark_img != 0)
print(coords)