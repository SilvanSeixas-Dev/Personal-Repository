import os
import shutil
import csv
from datetime import datetime

# ---- Configurações do sistema ----

base_folder = r"endereço do repositorio"
messy_folder = os.path.join(base_folder, "messy_folder")
organize_folder = os.path.join(base_folder, "organize_folder")


# SEGURANÇA: Mantenha True para testar sem mover nada. 
# Mude para False apenas quando tiver certeza absoluta!

simulation_mode = True

# Extensões e arquivos internos do MEGAsync/Sistema que NUNCA devem ser tocados
extension_ignore ={".mega", ".getxfer", ".putxfer", ".tmp", ".part", ".crdownload"}
name_ignore = {".debris", "desktop.ini", "thumbs.db", ".ds_store"}

def now_str():
    return datetime.now() .strftime("%Y-%m-%d  %H: %M: %S")

def create_secure_path (pasta_destino, nome_arquivo):
    caminho_final = os.path.join(pasta_destino, nome_arquivo)
    if not os.path.exists(caminho_final):
        return caminho_final

    base_name, extension = os.path.splitext(nome_arquivo)
    contador = 1
    while True:
        new_name = f"{base_name}_duplicado{contador}{extension}"
        new_path = os.path.join(pasta_destino, new_name)
        if not os.path.exists(new_path):
            return new_path
        contador += 1

def organize_files():
    if not os.path.exists(messy_folder):
        print(f"[ERRO] A pasta de origem não existe: {messy_folder}")
        return
        
    os.makedirs(organize_folder, exist_ok=True)

    # Cria um arquivo de Log (Auditoria) com data e hora
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    arquivo_log = os.path.join(organize_folder, f"auditoria_organização_{timestamp}.csv")

    with open (arquivo_log, mode = "w", newline = "", encoding = "utf-8-sig") as log_file:
        writer = csv.writer(log_file, delimiter = ";")
        writer.writerow(["Data_Hora", "Status", "Arquivo_Original", "Caminho_Origem", "Caminho_Destino"])

        for arquivo in os.listdir(messy_folder):
            source_path = os.path.join(messy_folder, arquivo)
# 1. Ignora pastas
            if not os.path.isfile(source_path):
                continue

# 2. Proteção contra arquivos ocultos e temporários do MEGAsync
            ext_full = os.path.splitext(arquivo)[1].lower()
            if arquivo.startswith(".") or arquivo.lower() in name_ignore or ext_full in extension_ignore:
                print(f"[IGNORADO - SISTEMA/MEGA] {arquivo}")
                writer.writerow([now_str(), "IGNORADO", arquivo, source_path,""])
                continue # <-- Essencial: pula para o próximo arquivo

# 3. Define a pasta de destino pela extensão
            extension = ext_full.lstrip(".")
            project = extension if extension else "Sem_extensão"
            destiny_folder = os.path.join(organize_folder, project)

# 4. Calcula o caminho seguro (sem risco de sobrescrever
            path_of_destiny = create_secure_path(destiny_folder, arquivo)

# 5. Executa ou Simula a movimentação com tratamento de erros
            try:
                if simulation_mode:
                    status = "SIMULADO (não movido)"
                    print(f"[SIMULAÇÃo] {arquivo} -> {path_of_destiny}")
                else:
                    os.makedirs(destiny_folder, exist_ok = True)
                    shutil.move(source_path, path_of_destiny)
                    status = "Movido com sucesso!!"
                    print(f"[OK] {arquivo} movido para: {project}")
                writer.writerow([now_str(), status, arquivo, source_path, path_of_destiny])

             
            except PermissionError:
                print(f"[ALERTA] Arquivo em uso, pulando para o próximo por questão de segurança: {arquivo}")
                writer.writerow([now_str(), "ALERTA_ARQUIVO_EM_USO", arquivo, source_path, path_of_destiny])
            except Exception as e:
                print(f"[ERRO] Ocorreu um erro ao mover o arquivo {arquivo}: {e}")
                writer.writerow([now_str(), "ERRO", arquivo, source_path, path_of_destiny])

            print(f"\nProcesso Finalizado! Relatório de auditoria gerado em: {arquivo_log}")

if __name__ == "__main__":
    organize_files()