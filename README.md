# GridScope Core

**GridScope Core** é uma API avançada e Dashboard para monitoramento de rede elétrica e simulação de geração distribuída. O sistema integra dados geográficos, métricas de rede e dados climáticos para fornecer insights em tempo real sobre a infraestrutura elétrica.

## 🚀 Funcionalidades

* **API RESTful (FastAPI)**: Endpoints para consulta de status da rede, ranking de subestações e simulação solar.
* **Dashboard Interativo (Streamlit)**: Visualização de dados em mapas (Folium), gráficos de consumo e métricas de Geração Distribuída (GD).
* **Processamento Geoespacial**: Geração automática de territórios de atuação de subestações utilizando Diagramas de Voronoi.
* **Simulação Solar**: Estimativa de geração fotovoltaica baseada em dados climáticos reais e previstos (via Open-Meteo API).

## 🛠️ Tecnologias Utilizadas

* **Backend**: Python, FastAPI, Uvicorn
* **Frontend/Dashboard**: Streamlit, Plotly, Folium
* **Geoprocessamento**: Geopandas, Shapely, Osmnx, Scipy (Voronoi)
* **Dados Externos**: Open-Meteo (Clima)

## 📦 Instalação

1. Clone este repositório:

    ```bash
    git clone <url-do-repositorio>
    cd gridScope-core
    ```

2. Crie um ambiente virtual (recomendado):

    ```bash
    python -m venv venv
    # Windows
    venv\Scripts\activate
    # Linux/Mac
    source venv/bin/activate
    ```

3. Instale as dependências:

    ```bash
    pip install -r requirements.txt
    ```

## ⚙️ Configuração

Crie um arquivo `.env` na raiz do projeto com as seguintes variáveis (baseado no `.env.example`):

```env
# Arquivos de Dados (Caminhos relativos ou absolutos)
FILE_GDB="Energisa_SE_6587_2023-12-31_V11_20250701-0833.gdb"
FILE_GEOJSON="subestacoes_logicas_aracaju.geojson"
FILE_MERCADO="perfil_mercado_aracaju.json"

# Configuração da Cidade Alvo para o Voronoi
CIDADE_ALVO="Aracaju, Sergipe, Brazil"
```

## ▶️ Como Usar

O projeto possui um script orquestrador que realiza todo o processo automaticamente: gera os territórios, processa os dados de mercado e inicia tanto a API quanto o Dashboard.

Basta rodar:

```bash
python run_all.py
```

O script irá:

1. **Gerar/Atualizar** os territórios (Voronoi).
2. **Processar** a análise de mercado.
3. **Iniciar** a API em `http://127.0.0.1:8000`.
4. **Abrir** o Dashboard automaticamente (ou em `http://localhost:8501`).

## 📂 Estrutura do Projeto

* `src/api.py`: Aplicação FastAPI principal.
* `src/dashboard.py`: Aplicação Streamlit.
* `src/config.py`: Gerenciamento de configurações e variáveis de ambiente.
* `src/utils.py`: Funções utilitárias para carregamento e fusão de dados.
* `src/modelos/processar_voronoi.py`: Script para geração da malha territorial.
* `dados/`: Diretório para armazenar arquivos GDB e JSON de entrada.

---
Desenvolvido como parte do projeto GridScope.
