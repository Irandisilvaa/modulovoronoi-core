"""
Script auxiliar para iniciar a API de IA manualmente.
Use este script se a API não estiver iniciando via run_all.py
"""
import sys
import os

DIR_RAIZ = os.path.dirname(os.path.abspath(__file__))
DIR_SRC = os.path.join(DIR_RAIZ, "src")
sys.path.insert(0, DIR_SRC)
sys.path.insert(0, DIR_RAIZ)

if __name__ == "__main__":
    try:
        import uvicorn
        from ai.ai_service import app
        
        print("🚀 Iniciando GridScope AI Service na porta 8001...")
        print("📁 Diretório de trabalho:", DIR_RAIZ)
        print("📁 Diretório src:", DIR_SRC)
        print("\n✅ Pressione Ctrl+C para parar\n")
        
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=8001,
            reload=False,
            log_level="info"
        )
    except ImportError as e:
        print(f"❌ Erro de importação: {e}")
        print("\n💡 Verifique se todas as dependências estão instaladas:")
        print("   pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Erro ao iniciar API: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

