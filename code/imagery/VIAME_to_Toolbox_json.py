#!/usr/bin/env python3
import csv
import json
import uuid
import os

def load_labelset(labelset_file):
    """
    Load the labelset JSON file, which is expected to be a list of dictionaries.
    Each dictionary must contain:
      - "id"
      - "short_label_code"
      - "long_label_code"
      - "color" (an array of four numbers)
      
    Returns a mapping from each label's short_label_code to its full dictionary.
    """
    with open(labelset_file, 'r') as f:
        data = json.load(f)
    
    if not isinstance(data, list):
        raise ValueError("Expected the labelset JSON to be a list of labels.")
    
    mapping = {}
    for label in data:
        mapping[label["short_label_code"]] = label
    return mapping

def convert_csv_to_coralnet(csv_file, label_mapping, base_path=""):
    """
    Read the VIAME CSV file and convert each row into a CoralNet rectangle annotation.
    
    The CSV file is assumed to have a header row with the following columns:
      Name, TL_x, TL_y, BR_x, BR_y, Label
      
    The 'base_path' parameter is prepended to the image name (from the "Name" column)
    if provided.
    
    Returns a dictionary where each key is an image path and each value is a list of
    annotation dictionaries.
    """
    coralnet_data = {}

    # Use utf-8-sig to automatically handle any BOM if present.
    with open(csv_file, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, delimiter=',', skipinitialspace=True)
        row_count = 0
        for row in reader:
            row_count += 1

            # Get the image name and prepend the base path if provided.
            image_name = row["Name"].strip()
            if base_path:
                image_path = os.path.join(base_path, image_name)
            else:
                image_path = image_name
            image_path = image_path.replace("\\", "/")  # Normalize path to forward slashes

            try:
                tl_x = max(0, float(row["TL_x"]))
                tl_y = max(0, float(row["TL_y"]))
                br_x = max(0, float(row["BR_x"]))
                br_y = max(0, float(row["BR_y"]))
            except ValueError as e:
                print(f"Error parsing coordinates in row {row_count} {row}: {e}")
                continue

            label_code = row["Label"].strip()
            if label_code not in label_mapping:
                print(f"Warning: Label '{label_code}' not found in labelset. Skipping row {row_count}: {row}")
                continue

            label_info = label_mapping[label_code]
            annotation_color = label_info.get("color", [255, 255, 255, 255])  # Default to white if missing
            annotation_color = label_info["color"]  # Keep as RGBA list [r, g, b, a]

            annotation = {
                "type": "RectangleAnnotation",
                "id": str(uuid.uuid4()),
                "label_short_code": label_info["short_label_code"],
                "label_long_code": label_info["long_label_code"],
                "annotation_color": annotation_color,
                "image_path": image_path,
                "label_id": label_info["id"],
                "data": {},
                "machine_confidence": {},
                "top_left": [tl_x, tl_y],
                "bottom_right": [br_x, br_y]
            }

            if image_path in coralnet_data:
                coralnet_data[image_path].append(annotation)
            else:
                coralnet_data[image_path] = [annotation]

    print(f"Processed {row_count} rows from CSV.")
    return coralnet_data

def main():
    print("=== VIAME CSV to CoralNet JSON Converter ===")
    
    csv_file = input("Enter the path to the VIAME CSV file: ").strip()
    base_path = input("Enter the base path for images (leave blank if full paths are in CSV): ").strip()
    labelset_file = input("Enter the path to the labelset JSON file: ").strip()
    output_file = input("Enter the desired output file path for the CoralNet JSON: ").strip()

    try:
        label_mapping = load_labelset(labelset_file)
    except Exception as e:
        print(f"Error loading labelset file: {e}")
        return

    try:
        coralnet_annotations = convert_csv_to_coralnet(csv_file, label_mapping, base_path)
    except Exception as e:
        print(f"Error processing CSV file: {e}")
        return

    try:
        with open(output_file, 'w') as f:
            json.dump(coralnet_annotations, f, indent=4)
        print(f"Conversion complete. Output saved to '{output_file}'.")
    except Exception as e:
        print(f"Error writing output file: {e}")

if __name__ == "__main__":
    main()
