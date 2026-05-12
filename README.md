# Address Cleaner

Script em Python para validar e padronizar dados de endereco da tabela `Enderecos` usando a API do ViaCEP.

O processo:
- le os registros em lote no banco PostgreSQL
- consulta o CEP no ViaCEP (com retry)
- usa cache local para evitar consultas repetidas
- identifica divergencias em `bairro`, `cidade` e `estado`
- marca ruas potencialmente problematicas para revisao manual
- gera um script SQL transacional com as atualizacoes

## Requisitos

- Python 3.10+
- Acesso ao banco PostgreSQL com a tabela `Enderecos`
- Conexao com internet para consultar o ViaCEP

Dependencias (em `requirements.txt`):
- `psycopg2-binary`
- `requests`
- `python-dotenv`

## Instalacao

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuracao

Crie um arquivo `.env` na raiz do projeto com:

```env
DB_HOST=localhost
DB_NAME=seu_banco
DB_USER=seu_usuario
DB_PASSWORD=sua_senha
DB_PORT=5432
```

## Como executar

```bash
python main.py
```

## Saidas geradas

Ao final da execucao, o script gera:
- `correcao_enderecos.sql`: arquivo com `BEGIN; ... COMMIT;` e updates
- `cache_cep.json`: cache local das respostas do ViaCEP

Tambem imprime um resumo com:
- total de registros processados
- quantidade de ruas problematicas
- quantidade de divergencias encontradas

## Observacoes importantes

- O script atualiza `bairro`, `cidade` e `estado` com base no ViaCEP quando encontra divergencia.
- O campo `rua` e mantido com o valor atual, mas pode ser comentado como "Rua problematica" para revisao manual.
- CEPs invalidos (diferentes de 8 digitos apos limpeza) sao ignorados.
- O processamento e feito em lotes (`BATCH_SIZE = 500`) e com atraso entre consultas (`REQUEST_DELAY = 0.25`) para reduzir carga na API.

## Estrutura do projeto

- `main.py`: script principal
- `requirements.txt`: dependencias Python
- `.gitignore`: arquivos ignorados pelo Git
