import os
import datetime

target = input('Enter full directory path: ')
prefix = input('Enter prefix: ')

os.chdir(target)
allfiles = os.listdir(target)

for filename in allfiles:
    if filename.lower().endswith('.thm'):
        print(f"Skipped {filename} as it has a '.THM' extension.")
        continue  # Skip .THM files

    c = os.path.getctime(filename)
    v = datetime.datetime.fromtimestamp(c)
    x = v.strftime('%Y_%m_%d-%H-%M-%S')
    new_name = prefix + x + ".MP4"

    if not os.path.exists(new_name):
        os.rename(filename, new_name)
    else:
        print(f"Skipped {filename} as {new_name} already exists.")