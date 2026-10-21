import os
import shutil

base_folder = r"location where the code is running"

messy_folder = os.path.join(base_folder, "messy folder")
organize_folder = os.path.join(base_folder, "organize folder")

os.makedirs(organize_folder, exist_ok = True)

for arquivo in os.listdir(messy_folder):
    source_path = os.path.join(messy_folder, arquivo)

    if not os.path.isfile(source_path):
        continue

    extension = os.path.splitext(arquivo)[1].lstrip(".").lower()

    project = extension if extension else "sem extensao"
    destiny_folder = os.path.join(organize_folder, project)
    os.makedirs(destiny_folder, exist_ok = True)

    path_of_destiny = os.path.join(destiny_folder, arquivo)

    shutil.move (source_path, path_of_destiny)
    print(f"{arquivo} foi movido para a pasta:{project}")