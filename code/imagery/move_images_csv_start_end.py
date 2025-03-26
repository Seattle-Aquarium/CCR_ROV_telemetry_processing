import pandas as pd
import os
import shutil

# Prompt user for file paths
csv_path = input("Enter the path to your CSV file: ").strip()
image_folder = input("Enter the path to your RAW images folder: ").strip()
destination_folder = input("Enter the path to the destination folder: ").strip()

# Load the CSV file and parse DateTime
df = pd.read_csv(csv_path)
df['DateTime'] = pd.to_datetime(df['Date'] + ' ' + df['Time'], errors='coerce')

# Filter out any rows with invalid dates
df = df.dropna(subset=['DateTime'])

# Automatically get the start and end times from the DateTime column
start_time = df['DateTime'].iloc[0]  # First timestamp in the CSV
end_time = df['DateTime'].iloc[-1]   # Last timestamp in the CSV

# Debugging output: Print the start and end times for reference
print(f"Start Time: {start_time}")
print(f"End Time: {end_time}")

# Filter rows within the specified time range
df_filtered = df[(df['DateTime'] >= start_time) & (df['DateTime'] <= end_time)]

# Ensure the destination folder exists
os.makedirs(destination_folder, exist_ok=True)

# Function to move images within the time range
def move_images_by_time_range(df_range):
    moved_images = 0
    for _, row in df_range.iterrows():
        image_time_str = row['DateTime'].strftime('%Y_%m_%d_%H-%M-%S')

        # Loop through image files in the folder
        for image_name in os.listdir(image_folder):
            if image_name.endswith('.GPR') and image_name.startswith(image_time_str):
                image_path = os.path.join(image_folder, image_name)
                destination_path = os.path.join(destination_folder, image_name)

                # Move the image and confirm
                shutil.move(image_path, destination_path)
                moved_images += 1
                print(f"Moved: {image_name}")
                break
        else:
            print(f"No matching image found for timestamp: {image_time_str}")

    print(f"\nTotal images moved to {destination_folder}: {moved_images}")

# Move images within the time range
move_images_by_time_range(df_filtered)
