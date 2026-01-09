import os
import shutil

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
cache_dirs = [
    '.streamlit/cache',
    '__pycache__',
    'src/__pycache__',
    'src/modelos/__pycache__',
    'src/etl/__pycache__',
]

print("🧹 Limpando cache do Streamlit...")

for cache_dir in cache_dirs:
    if os.path.exists(cache_dir):
        try:
            shutil.rmtree(cache_dir)
            print(f"  ✅ Removido: {cache_dir}")
        except Exception as e:
            print(f"  ⚠️  Erro ao remover {cache_dir}: {e}")
    else:
        print(f"  ℹ️  Não existe: {cache_dir}")

print("\n✅ Cache limpo!")
print("\n🚀 Agora execute:")
print("   streamlit run src/dashboard.py --server.runOnSave=false")
