import cv2
import os
import sys
import argparse

def extractImages(pathIn, pathOut):
	count = 0
	vidcap = cv2.VideoCapture('/Users/meganwilliams/Library/CloudStorage/OneDrive-Personal/Imagery/2022_8_15/vignettes/clip_for_CoralNet.mp4')
	success,image = vidcap.read()
	success = True
	while success:
		vidcap.set(cv2.CAP_PROP_POS_MSEC,(count*1000)) 
		success,image = vidcap.read()
		print('Read a new frame: ', success)
		cv2.imwrite( '/Users/meganwilliams/Library/CloudStorage/OneDrive-Personal/Imagery/2022_08_15/vignettes/2022_08_15_10-01-31_' + "%d.jpg" % count, image)     # save frame as JPEG file
		count = count + 30 #every 30 seconds 

	    

if __name__=="__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--pathIn", help="path to video")
    a.add_argument("--pathOut", help="path to images")
    args = a.parse_args()
    print(args)
    extractImages(args.pathIn, args.pathOut)