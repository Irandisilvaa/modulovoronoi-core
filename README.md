# GridScope Core

**GridScope Core** é uma plataforma avançada de monitoramento de redes elétricas e simulação de geração distribuída.
O sistema utiliza uma arquitetura moderna orientada a serviços para processar dados geoespaciais e fornecer insights em tempo real.

---

## 🚀 Funcionalidades

- **API RESTful (FastAPI)**  
  Endpoints otimizados para consulta do status da rede com **Cache L1 (Redis)**.

- **Dashboard Interativo (Streamlit)**  
  Visualização de dados em mapas, análise de mercado e simulação solar.

- **Processamento Geoespacial (PostGIS)**  
  Cálculo de territórios Voronoi e junções espaciais realizadas diretamente no banco de dados.

- **Simulação Solar com IA**  
  Estimativa de geração fotovoltaica baseada em dados climáticos reais (Open-Meteo) e perfis de consumo reais.

---

## 🛠️ Arquitetura Técnica

O sistema foi migrado para uma arquitetura robusta baseada em banco de dados:

- **Database:** PostgreSQL 15 + PostGIS (Armazenamento Centralizado)
- **Cache:** Redis 7 (Aceleração de API - Respostas em <50ms)
- **Backend:** Python 3.10+, FastAPI
- **Frontend:** Streamlit
- **Infraestrutura:** Docker Compose

---

## ⚙️ Instalação (Docker - Recomendado)

A forma padrão de execução é via Docker, que sobe automaticamente o Banco, Redis, API e Dashboard.

### 1. Configuração

Clone o repositório e configure o `.env`:

```bash
git clone <url-do-repositorio>
cd gridScope-core
# Crie o arquivo .env baseado no .env.example
# Certifique-se de configurar DATABASE_URL e REDIS_HOST
```

### 2. Execução

```bash
docker-compose up --build
```

### 3. Acessos

- **Dashboard:** [http://localhost:8501](http://localhost:8501)
- **API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## � Ferramentas de Manutenção

O projeto inclui scripts utilitários para gerenciamento do banco de dados:

- `python backup_db.py`: Gera backup completo do banco PostgreSQL (salva em `backups/`).
- `python criar_indices.py`: Recria índices de performance nas tabelas do banco.

---

## 📂 Estrutura do Projeto

```text
gridScope-core/
├── src/
│   ├── api.py            # API com Cache Redis
│   ├── database.py       # Camada de Acesso a Dados (PostgreSQL)
│   ├── cache_redis.py    # Módulo de Cache L1
│   ├── etl/              # Scripts de Carga e Migração
│   └── modelos/          # Regras de Negócio (Voronoi, Mercado)
│
├── dados/                # (Obsoleto - Dados migrados para o Banco)
├── docker-compose.yml    # Orquestração (App, DB, Redis)
├── requirements.txt
└── README.md
```

---

**Responsável Técnico:** Guilherme Araújo
**Atualizado em:** Janeiro/2026
