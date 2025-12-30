import subprocess
import sys
import time
import os

# Define os caminhos base
DIR_RAIZ = os.path.dirname(os.path.abspath(__file__))
DIR_SRC = os.path.join(DIR_RAIZ, "src")
PYTHON_EXEC = sys.executable

def get_env_with_src():
    """
    Cria uma cópia das variáveis de ambiente e adiciona a pasta 'src' ao PYTHONPATH.
    Isso garante que 'import config' e 'import utils' funcionem em qualquer script.
    """
    env = os.environ.copy()
    # Adiciona DIR_SRC ao PYTHONPATH existente (ou cria um novo)
    original_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{DIR_SRC}{os.pathsep}{original_path}"
    return env

def run_step(script_name, description):
    """
    Roda um script garantindo que ele enxerga o 'config.py'.
    """
    print(f"🔄 {description}...")
    
    # Busca o caminho do script. Tenta em 'modelos' primeiro, depois na raiz de 'src' ou onde for necessário
    # Para o Voronoi e Análise, sabemos que estão em src/modelos
    script_path = os.path.join(DIR_SRC, "modelos", script_name)
    
    if not os.path.exists(script_path):
        print(f"❌ Erro: Arquivo {script_name} não encontrado em {script_path}")
        sys.exit(1)

    # Roda o script passando o ambiente modificado (env)
    resultado = subprocess.run(
        [PYTHON_EXEC, script_path], 
        env=get_env_with_src()  # <--- AQUI ESTÁ A CORREÇÃO MÁGICA
    )
    
    if resultado.returncode == 0:
        print("✅ Sucesso!")
    else:
        print(f"❌ Falha ao executar {script_name}. Verifique o erro acima.")
        sys.exit(1)

def start_api():
    print("🚀 Iniciando API (Backend)...")
    # A API roda como módulo (-m), então o Python já costuma resolver bem, 
    # mas forçar o PYTHONPATH garante segurança extra.
    processo = subprocess.Popen(
        [PYTHON_EXEC, "-m", "uvicorn", "src.api:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=DIR_RAIZ,
        env=get_env_with_src()
    )
    return processo

def start_dashboard():
    print("📊 Iniciando Dashboard (Frontend)...")
    script_path = os.path.join(DIR_SRC, "dashboard.py")
    processo = subprocess.Popen(
        [PYTHON_EXEC, "-m", "streamlit", "run", script_path],
        cwd=DIR_RAIZ,
        env=get_env_with_src()
    )
    return processo

if __name__ == "__main__":
    print("--- ⚡ INICIANDO SISTEMA GRIDSCOPE COMPLETO (REFATATORADO) ⚡ ---")
    print(f"📂 Raiz do Projeto: {DIR_RAIZ}")
    print(f"📂 Pasta Fonte (SRC): {DIR_SRC}")
    
    # PASSO 1: Gerar as Áreas (Voronoi)
    run_step("processar_voronoi.py", "[1/3] Gerando Territorios (Voronoi)")
    
    # PASSO 2: Análise de Mercado
    run_step("analise_mercado.py", "[2/3] Cruzando Dados de Mercado")
    
    # PASSO 3: Servidores
    print("🔄 [3/3] Subindo Servidores...")
    api_proc = start_api()
    time.sleep(3) # Espera a API respirar
    dash_proc = start_dashboard()
    
    print("\n✅ TUDO ONLINE! (Ctrl+C para parar)")
    
    try:
        while True:
            time.sleep(1)
            if api_proc.poll() is not None:
                print("⚠️ API caiu!")
                break
            if dash_proc.poll() is not None:
                print("⚠️ Dashboard caiu!")
                break
    except KeyboardInterrupt:
        print("\n🛑 Encerrando tudo...")
        api_proc.terminate()
        dash_proc.terminate()