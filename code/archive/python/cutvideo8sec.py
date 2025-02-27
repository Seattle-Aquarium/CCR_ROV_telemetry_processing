import cv2
import tkinter as tk
from tkinter import filedialog
import os

root = tk.Tk()
root.withdraw()

file_path = filedialog.askopenfilename()
print(file_path)
cap = cv2.VideoCapture(file_path)
fps = int(cap.get(cv2.CAP_PROP_FPS))
frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

save_directory = filedialog.askdirectory()

# Modify the script to keep every 8th image and remove the rest
for i in range(int(frame_count/fps)):
    arr_frame=[]
    arr_lap=[]
    for j in range(fps):
        success, frame = cap.read()
        laplacian = cv2.Laplacian(frame, cv2.CV_64F).var()
        arr_lap.append(laplacian)
        arr_frame.append(frame)
    
    # Check if the current frame index is a multiple of 8
    if i % 8 == 0:
        selected_frame = arr_frame[arr_lap.index(max(arr_lap))]
        cv2.imwrite(os.path.join(save_directory, f'{i}.jpg'), selected_frame)
    else:
        # Skip frames that are not multiples of 8
        continue