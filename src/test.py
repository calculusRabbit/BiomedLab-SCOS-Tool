import cv2 
vid = cv2.VideoCapture(0)
ret, frame = vid.read()
gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
heat = cv2.applyColorMap(gray, cv2.COLORMAP_JET)
print(heat)