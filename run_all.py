import subprocess
import sys
import time
import os
import logging
from datetime import datetime

DIR_RAIZ = os.path.dirname(os.path.abspath(__file__))
DIR_SRC = os.path.join(DIR_RAIZ, "src")
DIR_LOGS = os.path.join(DIR_RAIZ, "logs")
PYTHON_EXEC = sys.executable

os.makedirs(DIR_LOGS, exist_ok=True)

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

def run_step(script_name, description):
    """Executa um script síncrono e registra o resultado."""
    logger.info(f"🔄 INICIANDO: {description} ({script_name})")
    
    script_path = os.path.join(DIR_SRC, "modelos", script_name)
    
    if not os.path.exists(script_path):
        logger.error(f"❌ ARQUIVO NÃO ENCONTRADO: {script_path}")
        sys.exit(1)

    inicio = time.time()
    resultado = subprocess.run(
        [PYTHON_EXEC, script_path], 
        env=get_env_with_src()
    )
    fim = time.time()
    duracao = round(fim - inicio, 2)
    
    if resultado.returncode == 0:
        logger.info(f"✅ SUCESSO: {description} concluído em {duracao}s.")
    else:
        logger.error(f"❌ FALHA: {script_name} falhou com código {resultado.returncode}.")
        sys.exit(1)

def start_api():
    """Inicia a API em subprocesso."""
    logger.info("🚀 INICIANDO API (Backend)...")
    log_api = open(os.path.join(DIR_LOGS, "api_service.log"), "w")
    
    processo = subprocess.Popen(
        [PYTHON_EXEC, "-m", "uvicorn", "src.api:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=DIR_RAIZ,
        env=get_env_with_src(),
        stdout=log_api, 
        stderr=log_api
    )
    return processo

def start_dashboard():
    """Inicia o Dashboard em subprocesso."""
    logger.info("📊 INICIANDO DASHBOARD (Frontend)...")
    processo = subprocess.Popen(
        [PYTHON_EXEC, "-m", "streamlit", "run", os.path.join(DIR_SRC, "dashboard.py")],
        cwd=DIR_RAIZ,
        env=get_env_with_src()
    )
    return processo

if __name__ == "__main__":
    logger.info("--- ⚡ INICIANDO SISTEMA GRIDSCOPE ⚡ ---")
    
    try:
        run_step("processar_voronoi.py", "Gerando Territorios")
        run_step("analise_mercado.py", "Cruzando Dados de Mercado")
        
        logger.info("🔄 Subindo Servidores de Aplicação...")
        api_proc = start_api()
        time.sleep(3) 
        dash_proc = start_dashboard()
        
        logger.info("✅ SISTEMA ONLINE (Ctrl+C para parar)")
        
        while True:
            time.sleep(1)
            if api_proc.poll() is not None:
                logger.warning("⚠️ ALERTA: O processo da API terminou inesperadamente.")
                break
            if dash_proc.poll() is not None:
                logger.warning("⚠️ ALERTA: O processo do Dashboard terminou inesperadamente.")
                break

    except KeyboardInterrupt:
        logger.info("\n🛑 Encerrando serviços...")
        api_proc.terminate()
        dash_proc.terminate()
        logger.info("👋 GridScope encerrado.")