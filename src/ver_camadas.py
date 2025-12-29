import os
import fiona

# Nome da sua pasta GDB (tem que ser igual ao que está na pasta dados)
NOME_PASTA_GDB = "Energisa_SE_6587_2023-12-31_V11_20250701-0833.gdb"

def listar_conteudo():
    # 1. Encontrar o caminho do arquivo
    dir_atual = os.path.dirname(os.path.abspath(__file__))
    caminho_gdb = os.path.join(dir_atual, "..", "dados", NOME_PASTA_GDB)
    
    print(f"📂 Inspecionando arquivo: {NOME_PASTA_GDB}")
    
    if not os.path.exists(caminho_gdb):
        print("❌ Erro: Arquivo não encontrado!")
        return

    # 2. Listar as camadas (Tabelas)
    try:
        camadas = fiona.listlayers(caminho_gdb)
        print(f"\n✅ ENCONTRADO! O arquivo possui {len(camadas)} camadas de dados.")
        print("="*60)
        print(f"{'NOME DA CAMADA':<30} | O QUE GERALMENTE SIGNIFICA")
        print("="*60)
        
        # Lista todas, mas destaca as importantes
        for camada in camadas:
            significado = ""
            if camada in ['SUB', 'SUBESTACAO']: significado = "⚡ Subestações (Já usamos)"
            elif camada in ['MT', 'SSDMT', 'SEG_MT']: significado = "🔌 Cabos de Média Tensão (Ruas)"
            elif camada in ['BT', 'SSDBT', 'SEG_BT']: significado = "🏠 Cabos de Baixa Tensão (Poste p/ casa)"
            elif camada in ['UC', 'UCMT', 'UCBT', 'CONSUMIDOR']: significado = "💎 PRECIOSO: Unidades Consumidoras!"
            elif camada in ['PONTO_NOTAVEL', 'TRAFO', 'UNTRMT']: significado = "⚙️ Transformadores"
            
            print(f"{camada:<30} | {significado}")
            
        print("="*60)
        
    except Exception as e:
        print(f"Erro ao ler camadas: {e}")

if __name__ == "__main__":
    listar_conteudo()