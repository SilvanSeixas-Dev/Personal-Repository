
"""
ORGANIZADOR DE ARQUIVOS PARA ESCRITÓRIO DE CONTABILIDADE

O que faz:
  1. Varre a pasta de origem E todas as subpastas.
  2. Descobre o ASSUNTO de cada arquivo (ex.: "João") e agrupa tudo em uma
     pasta com esse nome, não importando se é relatório, certificado etc.
  3. Nunca sobrescreve nem perde arquivos: nomes repetidos ganham _001, _002...
  4. Gera um log CSV de auditoria (permite DESFAZER tudo depois).

Uso:
  python organizador_contabil.py                      -> apenas SIMULA
  python organizador_contabil.py --executar           -> move de verdade
  python organizador_contabil.py --desfazer LOG.csv   -> devolve os arquivos
"""

import argparse
import csv
import hashlib
import os
import re
import shutil
import unicodedata
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher

# =====================================================================
# 1. CONFIGURAÇÕES
# =====================================================================
BASE_FOLDER = r"local do repositório"
SOURCE_FOLDER = os.path.join(BASE_FOLDER, "messy_folder")      # bagunça
DEST_FOLDER = os.path.join(BASE_FOLDER, "organize_folder")     # organizado

# SEGURANÇA: True = só simula. Também pode usar --executar na linha de comando.
SIMULATION_MODE = True

# Sensibilidade para juntar assuntos parecidos (0 a 1).
# 1.0 desliga a comparação aproximada. Valores baixos arriscam juntar
# clientes diferentes (ex.: "Maria Silva" e "Mario Silva").
FUZZY_THRESHOLD = 0.93

# Subpastas por tipo dentro de cada assunto (Relatorios, Contratos...)?
SUBFOLDER_BY_DOC_TYPE = False

# Calcula SHA-256 para avisar no log quando dois arquivos são idênticos.
# Atenção: lê o conteúdo de todos os arquivos (lento; em pastas "somente na
# nuvem" do OneDrive pode forçar o download).
DETECT_IDENTICAL = False

# Remove subpastas vazias da origem depois de mover (só no modo real).
REMOVE_EMPTY_FOLDERS = False

FALLBACK_FOLDER = "Sem_Assunto"
AUDIT_FOLDER = "_auditoria"      # dentro do destino

# Arquivos internos do MEGAsync / sistema / Office que NUNCA são tocados
IGNORE_EXTENSIONS = {".mega", ".getxfer", ".putxfer", ".tmp", ".part",
                     ".crdownload", ".lnk"}
IGNORE_NAMES = {".debris", "desktop.ini", "thumbs.db", ".ds_store"}

# =====================================================================
# 2. DICIONÁRIOS DA CONTABILIDADE
#    Palavras que descrevem o TIPO do documento (não o assunto/cliente).
#    Escritas sem acento e em minúsculas. Adapte à realidade do escritório.
# =====================================================================
TYPE_KEYWORDS = {
    "Relatorios": {"relatorio", "relatorios", "parecer", "laudo"},
    "Certificados": {"certificado", "certificados", "certidao", "certidoes",
                     "cnd"},
    "Notas_Fiscais": {"nota", "notas", "fiscal", "fiscais", "nf", "nfe",
                      "nfse", "danfe"},
    "Contratos": {"contrato", "contratos", "aditivo", "distrato",
                  "procuracao", "alteracao", "estatuto"},
    "Contabil": {"balanco", "balancete", "dre", "razao", "diario", "livro",
                 "conciliacao"},
    "Guias_Impostos": {"guia", "guias", "darf", "gps", "fgts", "inss", "dctf",
                       "irpf", "irpj", "iss", "icms", "pis", "cofins",
                       "imposto", "impostos", "simples", "sped", "ecd", "ecf"},
    "Folha_Pagamento": {"holerite", "holerites", "folha", "ferias", "rescisao",
                        "esocial", "rais", "caged"},
    "Financeiro": {"extrato", "extratos", "boleto", "boletos", "recibo",
                   "recibos", "comprovante", "comprovantes", "fatura",
                   "faturas", "pagamento"},
    "Documentos_Pessoais": {"documento", "documentos", "doc", "docs", "rg",
                            "cpf", "cnh", "identidade", "declaracao",
                            "declaracoes"},
}

EXTRA_NOISE = {
    "copia", "copy", "final", "novo", "nova", "new", "scan", "scanned",
    "digitalizado", "versao", "rev", "revisado", "anexo", "ref", "referente",
    "ano", "mes", "arquivo", "imagem", "img", "foto", "pdf",
    "janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho",
    "agosto", "setembro", "outubro", "novembro", "dezembro",
}

STOPWORDS = {"de", "da", "do", "dos", "das", "e", "a", "o", "as", "os", "em",
             "para", "por", "com", "no", "na", "nos", "nas", "ao", "the"}

DOC_WORDS = set().union(*TYPE_KEYWORDS.values()) | EXTRA_NOISE


# =====================================================================
# 3. FUNÇÕES DE TEXTO: normalização e extração do assunto
# =====================================================================
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize(text):
    """'João' -> 'joao' (minúsculas, sem acentos) para comparar nomes."""
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def words_of(text):
    """Divide em palavras. Retorna [(normalizada, original), ...]."""
    return [(normalize(w), w) for w in re.findall(r"[^\W_]+", text)]


def is_noise(norm):
    """Palavra que NÃO identifica o assunto (tipo de doc., data, versão...)."""
    return (len(norm) < 2
            or norm.isdigit()
            or norm in STOPWORDS
            or norm in DOC_WORDS
            or re.fullmatch(r"v\d+", norm) is not None)


def extract_subject(filename, rel_dir):
    """
    Descobre o assunto:
      1º) pelas palavras restantes no NOME do arquivo;
      2º) se nada sobrar, pelo nome da PASTA onde ele estava (da mais
          próxima para a mais distante);
      3º) se ainda assim nada, devolve lista vazia (-> Sem_Assunto).
    Retorna (palavras, fonte).
    """
    stem = os.path.splitext(filename)[0]
    pairs = [p for p in words_of(stem) if not is_noise(p[0])]
    if pairs:
        return pairs, "nome do arquivo"

    if rel_dir not in ("", "."):
        for part in reversed(rel_dir.split(os.sep)):
            pairs = [p for p in words_of(part) if not is_noise(p[0])]
            if pairs:
                return pairs, "pasta de origem"
    return [], "sem assunto"


def detect_doc_type(filename):
    """Classifica o tipo do documento (usado no log e nas subpastas)."""
    for norm, _ in words_of(os.path.splitext(filename)[0]):
        for tipo, palavras in TYPE_KEYWORDS.items():
            if norm in palavras:
                return tipo
    return "Outros"


def safe_folder_name(name):
    """Remove caracteres proibidos no Windows e limita o tamanho."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip(" .")
    return name[:80] or FALLBACK_FOLDER


# =====================================================================
# 4. AGRUPAMENTO DE ASSUNTOS (igual ou parecido)
# =====================================================================
class SubjectResolver:
    """
    Garante que 'João Silva', 'silva joao' e 'Joao Silva' caiam na MESMA
    pasta. A chave ignora acentos, maiúsculas e a ordem das palavras.
    """

    def __init__(self):
        self.folders = {}   # chave -> nome da pasta

    @staticmethod
    def key_of(pairs):
        return " ".join(sorted(p[0] for p in pairs))

    def seed_from_destination(self, dest):
        """Reaproveita pastas que já existem no destino (execuções antigas)."""
        if not os.path.isdir(dest):
            return
        for name in os.listdir(dest):
            if name.startswith("_") or name == FALLBACK_FOLDER:
                continue
            if os.path.isdir(os.path.join(dest, name)):
                pairs = [p for p in words_of(name) if not is_noise(p[0])]
                if pairs:
                    self.folders.setdefault(self.key_of(pairs), name)

    def resolve(self, pairs):
        key = self.key_of(pairs)
        if key in self.folders:
            return self.folders[key]

        # Comparação aproximada (tolera pequenos erros de digitação)
        melhor, melhor_nota = None, 0.0
        for existente in self.folders:
            nota = SequenceMatcher(None, key, existente).ratio()
            if nota > melhor_nota:
                melhor, melhor_nota = existente, nota
        if melhor and melhor_nota >= FUZZY_THRESHOLD:
            self.folders[key] = self.folders[melhor]
            return self.folders[melhor]

        nome = safe_folder_name(" ".join(p[1].capitalize() for p in pairs))
        self.folders[key] = nome
        return nome


# =====================================================================
# 5. SEGURANÇA DE ARQUIVOS: nomes únicos, hash, ignorados
# =====================================================================
def unique_path(folder, filename, reserved):
    """
    Devolve um caminho que NÃO existe e NÃO foi reservado nesta execução.
    Se o nome já existir: arquivo.pdf -> arquivo_001.pdf -> arquivo_002.pdf
    O conjunto 'reserved' faz isso funcionar também na simulação.
    """
    def ocupado(caminho):
        return os.path.exists(caminho) or os.path.normcase(caminho) in reserved

    candidato = os.path.join(folder, filename)
    if ocupado(candidato):
        base, ext = os.path.splitext(filename)
        n = 1
        while True:
            candidato = os.path.join(folder, f"{base}_{n:03d}{ext}")
            if not ocupado(candidato):
                break
            n += 1
    reserved.add(os.path.normcase(candidato))
    return candidato


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def is_ignored(name):
    ext = os.path.splitext(name)[1].lower()
    return (name.startswith(".")
            or name.startswith("~$")          # temporários do Office
            or name.lower() in IGNORE_NAMES
            or ext in IGNORE_EXTENSIONS)


def scan_files(source, dest):
    """Percorre origem e subpastas, pulando o destino e pastas de sistema."""
    dest_n = os.path.normcase(os.path.abspath(dest))
    for root, dirs, files in os.walk(source):
        dirs[:] = sorted(
            d for d in dirs
            if not d.startswith(".")
            and d.lower() not in IGNORE_NAMES
            and os.path.normcase(os.path.abspath(os.path.join(root, d))) != dest_n
        )
        for name in sorted(files):
            yield root, name


def remove_empty_dirs(source, dest):
    dest_n = os.path.normcase(os.path.abspath(dest))
    source_n = os.path.normcase(os.path.abspath(source))
    removidas = 0
    for dirpath, _, _ in os.walk(source, topdown=False):
        p = os.path.normcase(os.path.abspath(dirpath))
        if p == source_n or p == dest_n or p.startswith(dest_n + os.sep):
            continue
        if not os.listdir(dirpath):
            try:
                os.rmdir(dirpath)
                removidas += 1
            except OSError:
                pass
    return removidas


# =====================================================================
# 6. PROCESSO PRINCIPAL
# =====================================================================
LOG_HEADER = ["Data_Hora", "Status", "Assunto", "Tipo_Documento",
              "Fonte_Assunto", "Arquivo_Original", "Arquivo_Final",
              "Caminho_Origem", "Caminho_Destino", "Tamanho_Bytes",
              "SHA256", "Duplicata_De"]


def organize(source, dest, simulate):
    source, dest = os.path.abspath(source), os.path.abspath(dest)

    # Validações ANTES de criar qualquer coisa
    if not os.path.isdir(source):
        print(f"[ERRO] A pasta de origem não existe: {source}")
        return
    if os.path.normcase(source) == os.path.normcase(dest):
        print("[ERRO] Origem e destino não podem ser a mesma pasta.")
        return

    audit_dir = os.path.join(dest, AUDIT_FOLDER)
    os.makedirs(audit_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(audit_dir, f"auditoria_{stamp}.csv")

    arquivos = list(scan_files(source, dest))
    print(f"{len(arquivos)} arquivo(s) encontrado(s). "
          f"Modo: {'SIMULAÇÃO' if simulate else 'REAL'}\n")

    resolver = SubjectResolver()
    resolver.seed_from_destination(dest)
    reserved, hashes = set(), {}
    stats, assuntos = Counter(), Counter()

    with open(log_path, "w", newline="", encoding="utf-8-sig") as log_file:
        writer = csv.writer(log_file, delimiter=";")
        writer.writerow(LOG_HEADER)

        for root, name in arquivos:
            src = os.path.join(root, name)
            rel_dir = os.path.relpath(root, source)

            # --- Ignorados: registrados, mas nunca movidos
            if is_ignored(name):
                print(f"[IGNORADO] {name}")
                writer.writerow([now_str(), "IGNORADO", "", "", "", name, "",
                                 src, "", "", "", ""])
                stats["IGNORADO"] += 1
                continue

            final = ""
            try:
                pairs, fonte = extract_subject(name, rel_dir)
                assunto = resolver.resolve(pairs) if pairs else FALLBACK_FOLDER
                tipo = detect_doc_type(name)

                pasta = os.path.join(dest, assunto)
                if SUBFOLDER_BY_DOC_TYPE:
                    pasta = os.path.join(pasta, tipo)

                final = unique_path(pasta, name, reserved)
                tamanho = os.path.getsize(src)

                digest, duplicata = "", ""
                if DETECT_IDENTICAL:
                    digest = file_hash(src)
                    primeiro = hashes.setdefault(digest, final)
                    duplicata = "" if primeiro == final else primeiro

                if simulate:
                    status = "SIMULADO"
                    print(f"[SIMULAÇÃO] {name} -> {assunto}/{os.path.basename(final)}")
                else:
                    os.makedirs(pasta, exist_ok=True)
                    shutil.move(src, final)
                    if not os.path.exists(final):
                        raise OSError("arquivo não encontrado no destino")
                    status = "MOVIDO"
                    print(f"[OK] {name} -> {assunto}/{os.path.basename(final)}")

                stats[status] += 1
                assuntos[assunto] += 1
                writer.writerow([now_str(), status, assunto, tipo, fonte, name,
                                 os.path.basename(final), src, final,
                                 tamanho, digest, duplicata])

            except PermissionError:
                print(f"[ALERTA] Arquivo em uso, mantido no lugar: {name}")
                stats["EM_USO"] += 1
                writer.writerow([now_str(), "ALERTA_ARQUIVO_EM_USO", "", "", "",
                                 name, "", src, final, "", "", ""])
            except Exception as e:
                print(f"[ERRO] {name}: {e}")
                stats["ERRO"] += 1
                writer.writerow([now_str(), "ERRO", "", "", "", name, "",
                                 src, final, "", "", str(e)])
            log_file.flush()   # o log fica íntegro mesmo se o script cair

    if REMOVE_EMPTY_FOLDERS and not simulate:
        print(f"\nPastas vazias removidas: {remove_empty_dirs(source, dest)}")

    print("\n" + "=" * 60)
    print("PROCESSO FINALIZADO")
    for status, qtd in stats.items():
        print(f"  {status}: {qtd}")
    print(f"  Pastas de assunto: {len(assuntos)}")
    print(f"  Log de auditoria: {log_path}")
    print("=" * 60)


# =====================================================================
# 7. DESFAZER: lê o log CSV e devolve cada arquivo ao lugar original
# =====================================================================
def desfazer(csv_path):
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        linhas = list(csv.DictReader(f, delimiter=";"))

    restaurados = 0
    for linha in reversed(linhas):
        if linha["Status"] != "MOVIDO":
            continue
        atual, original = linha["Caminho_Destino"], linha["Caminho_Origem"]
        if not os.path.exists(atual):
            print(f"[ALERTA] Não encontrado (foi movido ou apagado?): {atual}")
            continue
        destino = unique_path(os.path.dirname(original),
                              os.path.basename(original), set())
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        shutil.move(atual, destino)
        restaurados += 1
        print(f"[RESTAURADO] {destino}")
    print(f"\n{restaurados} arquivo(s) restaurado(s).")


# =====================================================================
# 8. LINHA DE COMANDO
# =====================================================================
def main():
    ap = argparse.ArgumentParser(description="Organizador para contabilidade")
    ap.add_argument("--origem", default=SOURCE_FOLDER)
    ap.add_argument("--destino", default=DEST_FOLDER)
    ap.add_argument("--executar", action="store_true",
                    help="move de verdade (sem isso, apenas simula)")
    ap.add_argument("--desfazer", metavar="LOG.csv",
                    help="restaura os arquivos a partir de um log de auditoria")
    args = ap.parse_args()

    if args.desfazer:
        desfazer(args.desfazer)
        return

    simulate = SIMULATION_MODE and not args.executar
    if not simulate:
        resp = input("ATENÇÃO: os arquivos serão MOVIDOS. "
                     "Digite SIM para continuar: ")
        if resp.strip().upper() != "SIM":
            print("Cancelado.")
            return
    organize(args.origem, args.destino, simulate)


if __name__ == "__main__":
    main()
