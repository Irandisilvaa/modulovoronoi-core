import subprocess
import sys
import time
import os
import logging
from datetime import datetime

DIR_RAIZ = os.path.dirname(os.path.abspath(__file__))
DIR_SRC = os.path.join(DIR_RAIZ, "src")
DIR_LOGS = os.path.join(DIR_RAIZ, "logs")

CAMINHO_MODELO_PKL = os.path.join(DIR_SRC, "ai", "modelo_consumo.pkl")

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


def run_script(script_path, description):
    """Função genérica para rodar scripts."""
    if not os.path.exists(script_path):
        logger.error(f"❌ ARQUIVO NÃO ENCONTRADO: {script_path}")
        return False

    inicio = time.time()
    logger.info(f"▶️ INICIANDO: {description}")

    resultado = subprocess.run([PYTHON_EXEC, script_path], env=get_env_with_src())

    duracao = round(time.time() - inicio, 2)
    if resultado.returncode == 0:
        logger.info(f"✅ SUCESSO: {description} ({duracao}s)")
        return True
    else:
        logger.error(f"❌ FALHA: {description} (Código {resultado.returncode})")
        return False


def start_api_process(module_name, port, log_filename, description):
    """Inicia um processo de API em background."""
    logger.info(f"🚀 SUBINDO {description} na porta {port}...")

    log_file = open(os.path.join(DIR_LOGS, log_filename), "w", encoding="utf-8")

    import platform
    workers = "1" if platform.system() == "Windows" else "4"

    env_vars = get_env_with_src()
    env_vars["PYTHONIOENCODING"] = "utf-8"

    processo = subprocess.Popen(
        [PYTHON_EXEC, "-m", "uvicorn", module_name, "--host", "0.0.0.0", "--port", str(port), "--workers", workers],
        cwd=DIR_RAIZ,
        env=env_vars,
        stdout=log_file,
        stderr=log_file
    )
    return processo


def run_pipeline():
    # Passo 0: Verificar atualizações na ANEEL (Monitor)
    logger.info("📡 Verificando atualizações na ANEEL...")
    run_script(os.path.join(DIR_SRC, "etl", "monitor_aneel.py"), "Monitor ANEEL")

    logger.info("📦 Migrando dados do GDB para PostgreSQL...")
    if not run_script(os.path.join(DIR_SRC, "etl", "migracao_db.py"), "Migração Database (GDB -> SQL)"):
        logger.error("🛑 Falha crítica na migração. Abortando inicialização.")
        sys.exit(1)

    run_script(os.path.join(DIR_SRC, "modelos", "processar_voronoi.py"), "Gerando Territórios (Voronoi)")

    run_script(os.path.join(DIR_SRC, "modelos", "analise_mercado.py"), "Análise de Mercado")


    logger.info("🧠 Treinando IA (Duck Curve)... Isso pode levar alguns segundos.")
    run_script(os.path.join(DIR_SRC, "ai", "train_model.py"), "Treinamento Modelo Random Forest")


if __name__ == "__main__":
    logger.info("--- ⚡ INICIANDO SISTEMA GRIDSCOPE (HACKATHON MODE) ⚡ ---")

    try:
        run_pipeline()

        logger.info("--- INICIANDO SERVIDORES ---")

        api_proc = start_api_process("src.api:app", 8000, "api_service.log", "API Principal")

        api_ai_proc = start_api_process("src.ai.ai_service:app", 8001, "api_ai.log", "API Inteligência Artificial")

        logger.info("⏳ Aguardando 12 segundos para carga completa dos modelos de IA...")
        time.sleep(12)

        logger.info("📊 Abrindo Dashboard...")
        dash_proc = subprocess.Popen(
            [PYTHON_EXEC, "-m", "streamlit", "run", os.path.join(DIR_SRC, "dashboard.py"), "--server.runOnSave",
             "false"],
            cwd=DIR_RAIZ,
            env=get_env_with_src()
        )

        logger.info("\n✅ SISTEMA TOTALMENTE ONLINE")
        logger.info("📝 Logs detalhados disponíveis na pasta /logs")
        logger.info("Press Ctrl+C para encerrar tudo.\n")

        while True:
            time.sleep(2)
            if api_proc.poll() is not None:
                logger.error("⚠️ CRITICAL: API Principal (8000) morreu! Verifique logs/api_service.log")
                break
            if api_ai_proc.poll() is not None:
                logger.error(
                    "⚠️ CRITICAL: API IA (8001) morreu! O Duck Curve não vai funcionar. Verifique logs/api_ai.log")
                break
            if dash_proc.poll() is not None:
                logger.warning("ℹ️ Dashboard fechado pelo usuário.")
                break

    except KeyboardInterrupt:
        logger.info("\n🛑 Encerrando serviços...")
        try:
            api_proc.terminate()
            api_ai_proc.terminate()
            dash_proc.terminate()
        except:
            pass
        logger.info("GridScope encerrado com sucesso.")