# File name is file_manager.py
# Locations as of 2025-01-15: 
# 	Seattle Aquarium Dropbox\Coastal_Climate_Resilience\SORT\code\Python\in_use\file_manager.py
#	Seattle Aquarium Dropbox\Coastal_Climate_Resilience\GitHub\Seattle_Aquarium_CCR_analytical_resources\code\file_manager.py

import os
import shutil
# import win32com.client
from pathlib import Path

# User enters file path to directory
dir_path = input('Enter file path to directory: ').strip()

# Displays user menu
def show_menu():
	print('\nSelect command:')
	print('1. Sort images')
	print('2. Delete directory')
	print('3. Create new directory')
	print('4. Change directory path')
	print('5. Exit')

### Operable Functions ###
# Function to copy images into 'testing' and 'training' folders | *requires nested 'edited' folder within given directory
def sort_images(folder):
	# Locates the 'edited' folder within the transect folders
	edited_dir_path = Path(folder) / "edited"
	if not edited_dir_path.exists():
		print(f"Error: No 'edited' folder found in {folder}")
		return

	# Creates a reference list of all images in the 'edited' folder
	image_list = [file for file in os.listdir(edited_dir_path)
		if file.lower().endswith('.jpg') and os.path.isfile(os.path.join(edited_dir_path, file))]

	# Creates 'testing' and 'training' folders
	testing_path = os.path.join(folder, 'testing')
	os.makedirs(testing_path, exist_ok = True)
	training_path = os.path.join(folder, 'training')
	os.makedirs(training_path, exist_ok = True)

	# Copies every third image to the 'testing' folder and all others to the 'training' folder
	for i, image in enumerate(image_list):
			edited = os.path.join(edited_dir_path, image)
			# previous version used shutil to make a separate image copy as shown below
			if i % 3 == 0:
				testing_folder = os.path.join(testing_path, image)
				shutil.copy(edited, testing_folder)
				# create_shortcut(edited, testing_path)
				# print(f"Added {image} shortcut to testing")
			else:
				training_folder = os.path.join(training_path, image)
				shutil.copy(edited, training_folder)
				# create_shortcut(edited, training_path)
				# print(f"Added {image} shortcut to training")

# Function to generate a shortcut to a file
def create_shortcut(target, destination):
	# Ensure the target file exists
	if not os.path.exists(target):
		print(f"Target file does not exist: {target}")
		return
	
	# Create a shortcut using COM interface
	shell = win32com.client.Dispatch("WScript.Shell")
	file_name = os.path.basename(target)
	shortcut_path = os.path.join(destination, os.path.splitext(file_name)[0]) + ".lnk"
	shortcut = shell.CreateShortCut(shortcut_path)
	shortcut.TargetPath = target
	shortcut.WorkingDirectory = os.path.dirname(target)
	shortcut.IconLocation = target
	shortcut.save()

# Function to delete file from file path
def delete_file(folder):
	if os.path.exists(folder):
		os.chmod(folder, 0o777) # changes folder permission to full access
	shutil.rmtree(folder)
	print(f"Successfully deleted {os.path.basename(folder)}")

# Function to create a new directory
def create_directory(name, path):
	new_dir_path = os.path.join(path, name)
	if not os.path.exists(new_dir_path):
		os.mkdir(new_dir_path)
		print(f"Successfully created directory '{name}' under '{path}'")
	else:
		print(f"Error: Directory '{name}' already exists at '{path}'")

# Function to change current working directory
def change_directory():
	delta_dir_path = input('Enter new directory path: ').strip()
	if os.path.isdir(delta_dir_path):
		return delta_dir_path
	else:
		print(f"Error: The directory '{delta_dir_path}' does not exist.")
		return None

### Execution of Command ###
# Operates user menu
def main():
	menu()

def menu():
	global dir_path
	while True:
		show_menu()
		try:
			command = int(input('\nInput: '))
		except ValueError:
			print("Invalid input, please enter a valid number.")
			continue
		# Calls function to sort images into generated 'testing' and 'training' folders
		if command == 1:
			for root in os.listdir(dir_path):
				pathway = os.path.join(dir_path, root)
				sort_images(pathway)
		# Calls function to delete a directory and its contents
		elif command == 2:
			print('Enter paths to directories that will be deleted')
			delete_this = input('Separate multiple paths with spaces: ').strip()
			print(f"\n*WARNING: File deletion is irreversible*\n'{os.path.basename(delete_this)}' and its contents will be permanently deleted\n")
			while True:
				confirm = input('Proceed with directory deletion (Y/N)?: ').strip()
				if confirm.lower() == 'y':
					delete_file(delete_this)
					break
				elif confirm.lower() == 'n':
					print('\nOperation canceled')
					break
				else:
					print("Invalid input, please enter 'y' or 'n'")
		# Calls function to create a new directory	
		elif command == 3:
			name_dir = input('Enter name for new directory: ').strip()
			create_directory(name_dir, dir_path)
		# Change directory
		elif command == 4:
			new_dir_path = change_directory()
			if new_dir_path:
				dir_path = new_dir_path
		# Terminate script
		elif command == 5:
			print("Exiting the program.")
			break
		else:
			print(f'\n{command} is invalid, please select a valid command.')
menu()
