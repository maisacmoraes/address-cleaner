import os
import psycopg2
import requests
import re
import time
import json
import unicodedata
from dotenv import load_dotenv

load_dotenv()

VIACEP_URL = "https://viacep.com.br/ws/{}/json/"
REQUEST_DELAY = 0.25
BATCH_SIZE = 500
ARQUIVO_SQL = "correcao_enderecos.sql"
CACHE_FILE = "cache_cep.json"

TERMOS_PROBLEMA = [
    "proximo", "próximo", "perto",
    "atras", "atrás",
    "ao lado", "lado de",
    "em frente", "fundos",
    "final da linha"
]


# ===============================
# UTILIDADES
# ===============================

def conectar():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=os.getenv("DB_PORT")
    )


def limpar_cep(cep):
    return re.sub(r"\D", "", cep or "")


def normalizar_texto(texto):
    if not texto:
        return ""
    texto = texto.strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto


def escape_sql(valor):
    if valor is None:
        return ""
    return valor.replace("'", "''")


def contem_termo_problema(texto):
    texto_normalizado = normalizar_texto(texto)
    for termo in TERMOS_PROBLEMA:
        if termo in texto_normalizado:
            return True
    return False


# ===============================
# VIA CEP COM RETRY
# ===============================

def consultar_cep(cep, tentativas=3):
    for tentativa in range(tentativas):
        try:
            response = requests.get(VIACEP_URL.format(cep), timeout=5)
            if response.status_code == 200:
                data = response.json()
                if "erro" not in data:
                    return data
        except:
            pass

        time.sleep(1)

    return None


# ===============================
# CACHE
# ===============================

def carregar_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def salvar_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# ===============================
# PROCESSAMENTO
# ===============================

def main():
    conn = conectar()
    cursor = conn.cursor()

    cache_cep = carregar_cache()
    sql_updates = []

    offset = 0
    total_processados = 0
    divergencias = 0
    ruas_problema = 0

    print("🚀 Iniciando processamento...\n")

    while True:
        cursor.execute("""
            SELECT id, rua, numero, complemento, bairro, cidade, estado, cep
            FROM "Enderecos"
            LIMIT %s OFFSET %s
        """, (BATCH_SIZE, offset))

        registros = cursor.fetchall()

        if not registros:
            break

        for id_, rua, numero, complemento, bairro, cidade, estado, cep in registros:
            total_processados += 1

            cep_limpo = limpar_cep(cep)
            if len(cep_limpo) != 8:
                continue

            # ===============================
            # CACHE CEP
            # ===============================
            if cep_limpo not in cache_cep:
                dados = consultar_cep(cep_limpo)
                if dados:
                    cache_cep[cep_limpo] = dados
                time.sleep(REQUEST_DELAY)

            dados = cache_cep.get(cep_limpo)
            if not dados:
                continue

            bairro_api = dados.get("bairro")
            cidade_api = dados.get("localidade")
            estado_api = dados.get("uf")

            # ===============================
            # Verifica divergência
            # ===============================
            divergencia = (
                normalizar_texto(bairro) != normalizar_texto(bairro_api) or
                normalizar_texto(cidade) != normalizar_texto(cidade_api) or
                normalizar_texto(estado) != normalizar_texto(estado_api)
            )

            rua_problema = (
                rua and (len(rua) > 45 or contem_termo_problema(rua))
            )

            if rua_problema:
                ruas_problema += 1
                sql_updates.append(f"-- Rua problemática (REVISAR MANUALMENTE)")
                sql_updates.append(f"-- ID: {id_}")
                sql_updates.append(f"-- Rua atual: {rua}\n")

            if divergencia:
                divergencias += 1

                sql_updates.append(f"""
UPDATE "Enderecos"
SET rua = '{escape_sql(rua)}',
    numero = '{escape_sql(numero)}',
    complemento = '{escape_sql(complemento)}',
    bairro = '{escape_sql(bairro_api)}',
    cidade = '{escape_sql(cidade_api)}',
    estado = '{escape_sql(estado_api)}'
WHERE id = '{id_}';
""")

        offset += BATCH_SIZE
        print(f"✔ Processados até agora: {total_processados}")

    salvar_cache(cache_cep)

    # ===============================
    # Gera SQL
    # ===============================
    with open(ARQUIVO_SQL, "w", encoding="utf-8") as f:
        f.write("-- Script gerado automaticamente\n\n")
        f.write("BEGIN;\n\n")
        for bloco in sql_updates:
            f.write(bloco + "\n")
        f.write("\nCOMMIT;\n")

    print("\n========== RESUMO ==========")
    print(f"Total processados: {total_processados}")
    print(f"Ruas problemáticas: {ruas_problema}")
    print(f"Divergências ViaCEP: {divergencias}")
    print(f"Arquivo SQL: {ARQUIVO_SQL}")
    print(f"Cache salvo: {CACHE_FILE}")
    print("============================\n")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()