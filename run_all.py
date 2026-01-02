import subprocess
import sys
import time
import os
import logging
from datetime import datetime

# --- CONFIGURAÇÕES DE DIRETÓRIO ---
DIR_RAIZ = os.path.dirname(os.path.abspath(__file__))
DIR_SRC = os.path.join(DIR_RAIZ, "src")
DIR_LOGS = os.path.join(DIR_RAIZ, "logs")
# Definindo onde o modelo fica para verificar se ele já existe
CAMINHO_MODELO_PKL = os.path.join(DIR_SRC, "ai", "modelo_consumo.pkl")

PYTHON_EXEC = sys.executable

os.makedirs(DIR_LOGS, exist_ok=True)

# --- CONFIGURAÇÃO DE LOG ---
nome_arquivo_log = f"{datetime.now().strftime('%Y-%m-%d')}_sistema.log"
caminho_log = os.path.join(DIR_LOGS, nome_arquivo_log)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(caminho_log, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("GridScope")

def get_env_with_src():
    """Configura variáveis de ambiente adicionando src ao PYTHONPATH."""
    env = os.environ.copy()
    original_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{DIR_SRC}{os.pathsep}{original_path}"
    return env

# --- FUNÇÕES EXECUTORAS ---

def run_etl(script_name, description):
    """Executa um script da pasta src/etl."""
    logger.info(f"INICIANDO ETL: {description} ({script_name})")
    
    script_path = os.path.join(DIR_SRC, "etl", script_name)
    
    if not os.path.exists(script_path):
        logger.error(f"ARQUIVO ETL NÃO ENCONTRADO: {script_path}")
        sys.exit(1)
        
    inicio = time.time()
    resultado = subprocess.run([PYTHON_EXEC, script_path], env=get_env_with_src())
    fim = time.time()
    
    duracao = round(fim - inicio, 2)
    if resultado.returncode == 0:
        logger.info(f"SUCESSO: {description} concluído em {duracao}s.")
    else:
        logger.error(f"FALHA: {script_name} falhou com código {resultado.returncode}.")
        sys.exit(1)

def run_step(script_name, description):
    """Executa um script da pasta modelos."""
    logger.info(f"INICIANDO MODELO: {description} ({script_name})")
    script_path = os.path.join(DIR_SRC, "modelos", script_name)
    
    if not os.path.exists(script_path):
        logger.error(f"ARQUIVO NÃO ENCONTRADO: {script_path}")
        sys.exit(1)
        
    inicio = time.time()
    resultado = subprocess.run([PYTHON_EXEC, script_path], env=get_env_with_src())
    fim = time.time()
    duracao = round(fim - inicio, 2)
    
    if resultado.returncode == 0:
        logger.info(f"SUCESSO: {description} concluído em {duracao}s.")
    else:
        logger.error(f"FALHA: {script_name} falhou com código {resultado.returncode}.")
        sys.exit(1)
        
def run_ai_training(script_name, description, forcar_treino=False):
    """Executa script de treinamento na pasta AI, APENAS SE NECESSÁRIO."""
    
    # --- NOVA LÓGICA: Verifica se o modelo já existe ---
    if os.path.exists(CAMINHO_MODELO_PKL) and not forcar_treino:
        logger.info(f"⏩ MODELO JÁ EXISTE: {description}. Pulando treinamento para inicializar rápido.")
        return
    # ----------------------------------------------------

    logger.info(f"🧠 TREINANDO IA: {description} ({script_name})")
    script_path = os.path.join(DIR_SRC, "ai", script_name)
    
    # Fallback caso esteja em modelos (compatibilidade)
    if not os.path.exists(script_path):
        script_path = os.path.join(DIR_SRC, "modelos", script_name)
        
    if not os.path.exists(script_path):
        logger.warning(f"Script de IA não encontrado: {script_path}. Pulando etapa.")
        return
        
    inicio = time.time()
    subprocess.run([PYTHON_EXEC, script_path], env=get_env_with_src())
    logger.info(f"SUCESSO: {description} finalizado em {round(time.time() - inicio, 2)}s.")

# --- INICIALIZADORES DE SERVIÇOS ---

def start_api():
    logger.info("INICIANDO API PRINCIPAL (Backend 8000)...")
    log_api = open(os.path.join(DIR_LOGS, "api_service.log"), "w")
    
    processo = subprocess.Popen(
        [PYTHON_EXEC, "-m", "uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"],
        cwd=DIR_RAIZ,
        env=get_env_with_src(),
        stdout=log_api, 
        stderr=log_api
    )
    return processo

def start_api_ai():
    logger.info("INICIANDO API IA (Backend 8001)...")
    log_ai = open(os.path.join(DIR_LOGS, "api_ai.log"), "w")
    
    processo = subprocess.Popen(
        [PYTHON_EXEC, "-m", "uvicorn", "src.ai.ai_service:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "4"],
        cwd=DIR_RAIZ,
        env=get_env_with_src(),
        stdout=log_ai, 
        stderr=log_ai
    )
    return processo

def start_dashboard():
    logger.info("INICIANDO DASHBOARD (Frontend)...")
    processo = subprocess.Popen(
        [PYTHON_EXEC, "-m", "streamlit", "run", os.path.join(DIR_SRC, "dashboard.py"), "--server.runOnSave", "false"],
        cwd=DIR_RAIZ,
        env=get_env_with_src()
    )
    return processo

# --- FLUXO PRINCIPAL ---

if __name__ == "__main__":
    logger.info("--- ⚡ INICIANDO SISTEMA GRIDSCOPE (MODO INTELIGENTE) ⚡ ---")
    try:
        # 1. Pipeline de ETL (Extração e Tratamento)
        run_etl("etl_ai_consumo.py", "ETL: Carga de Consumo Real (BDGD)") 
        
        # 2. Processamento Geoespacial e Mercado
        run_step("processar_voronoi.py", "Gerando Territorios (Voronoi)")
        # run_step("analise_mercado.py", "Cruzando Dados de Mercado") # Descomente se necessário
        
        # 3. Treinamento de IA (Verifica se precisa treinar ou se já existe)
        run_ai_training("train_model.py", "Treinamento Modelo Duck Curve", forcar_treino=False)
        
        # 4. Inicialização dos Servidores
        logger.info("Subindo Servidores de Aplicação...")
        api_proc = start_api()   
        api_ai_proc = start_api_ai() 
        
        time.sleep(5) # Aguarda APIs subirem
        dash_proc = start_dashboard()
        
        logger.info("✅ SISTEMA ONLINE (Ctrl+C para parar)")
        
        # Loop de Monitoramento
        while True:
            time.sleep(1)
            if api_proc.poll() is not None:
                logger.warning("⚠️ ALERTA: A API Principal (8000) caiu.")
                break
            if api_ai_proc.poll() is not None:
                logger.warning("⚠️ ALERTA: A API de IA (8001) caiu.")
                break
            if dash_proc.poll() is not None:
                logger.warning("⚠️ ALERTA: O Dashboard fechou.")
                break
                
    except KeyboardInterrupt:
        logger.info("\nEncerrando serviços...")
        try:
            api_proc.terminate()
            api_ai_proc.terminate() 
            dash_proc.terminate()
        except:
            pass
        logger.info("GridScope encerrado.")