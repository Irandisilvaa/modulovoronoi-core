import requests
import json
import os
import sys
import re
import zipfile
import shutil
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import DIR_DADOS, ANEEL_API_HUB_URL, DISTRIBUIDORA_ALVO

def baixar_e_extrair(url, destino):
    print(f"\n ⬇INICIANDO DOWNLOAD...")
    print(f"Origem: {url}")
    
    caminho_zip = os.path.join(destino, "temp_download.zip")
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        
        with requests.get(url, stream=True, headers=headers, timeout=120) as r:
            r.raise_for_status()
            
            ct = r.headers.get('content-type', '').lower()
            if 'html' in ct:
                print(f"ALERTA: O link retornou uma página HTML ({ct}). Pode não ser um ZIP direto.")
            
            total_size = int(r.headers.get('content-length', 0))
            baixado = 0
            
            with open(caminho_zip, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    baixado += len(chunk)
                    if total_size > 0:
                        percent = int((baixado / total_size) * 100)
                        print(f"\r    Progresso: {percent}% ", end="")
        print("") 

        if not zipfile.is_zipfile(caminho_zip):
            print("❌ ERRO: O arquivo baixado não é um ZIP válido.")
            with open(caminho_zip, 'r', errors='ignore') as f:
                print(f"    Conteúdo (início): {f.read(300)}...")
            os.remove(caminho_zip)
            return None

        print(f"Extraindo para: {destino} ...")
        gdb_extraido = None
        
        with zipfile.ZipFile(caminho_zip, 'r') as zip_ref:
            zip_ref.extractall(destino)
            for nome in zip_ref.namelist():
                if '.gdb' in nome:
                    partes = nome.split('/')
                    for p in partes:
                        if p.endswith('.gdb'):
                            gdb_extraido = p
                            break
                if gdb_extraido: break
        
        os.remove(caminho_zip)
        
        if gdb_extraido:
            print("Sucesso!")
            return gdb_extraido
        else:
            print("ZIP extraído, mas a pasta '.gdb' não foi identificada automaticamente.")
            return "VERIFIQUE_A_PASTA_DADOS"

    except Exception as e:
        print(f"\nFalha técnica: {e}")
        if os.path.exists(caminho_zip):
            os.remove(caminho_zip)
        return None

def verificar_aneel():
    print(f"Monitor ANEEL (ArcGIS Hub)")
    print(f"Alvo: '{DISTRIBUIDORA_ALVO}'")
    
    try:
        params = {"q": DISTRIBUIDORA_ALVO, "limit": 30}
        response = requests.get(ANEEL_API_HUB_URL, params=params, timeout=15)
        
        if response.status_code != 200:
            print(f"Erro API: {response.status_code}")
            return

        resultados = response.json().get('features', [])
        if not resultados:
            print("Nenhum resultado encontrado.")
            return

        print(f"Analisando {len(resultados)} itens...")

        candidatos = []
        termos = DISTRIBUIDORA_ALVO.upper().split()

        for item in resultados:
            props = item.get('properties', {})
            nome = props.get('title', 'Sem Nome').upper()
            
            if all(t in nome for t in termos):
                candidatos.append(props)

        if not candidatos:
            print("Nenhum arquivo compatível.")
            return

        def criterio(item):
            nome = item.get('title', '')
            ano = 0
            match = re.search(r'202[0-9]', nome)
            if match: ano = int(match.group(0))
            tem_link = 1 if " - Link" in nome else 0
            return (ano, tem_link, nome)

        candidatos.sort(key=criterio, reverse=True)
        vencedor = candidatos[0]

        nome_final = vencedor.get('title')
        id_arquivo = vencedor.get('id')
        data_raw = vencedor.get('updated')
        url_original = vencedor.get('url')
        
        if " - Link" in nome_final:
            if '/documents/' in url_original:
                url_download = f"https://www.arcgis.com/sharing/rest/content/items/{id_arquivo}/data"
            else:
                url_download = url_original
        else:
            url_download = f"https://dadosabertos-aneel.opendata.arcgis.com/datasets/{id_arquivo}_0.geodatabase"

        print(f"\nARQUIVO VENCEDOR:")
        print(f"{nome_final}")
        
        arquivo_ctrl = os.path.join(DIR_DADOS, "metadata_aneel.json")
        baixar = True
        
        if os.path.exists(arquivo_ctrl):
            with open(arquivo_ctrl, 'r') as f:
                meta = json.load(f)
                if meta.get('id') == id_arquivo and meta.get('folder_name'):
                    print("⏸Versão já existente.")
                    baixar = False
        
        if baixar:
            print("NOVA VERSÃO! Baixando...")
            print(f"Tentando baixar de: {url_download}")
            
            nome_gdb = baixar_e_extrair(url_download, DIR_DADOS)
            
            if nome_gdb:
                with open(arquivo_ctrl, 'w') as f:
                    json.dump({
                        'name': nome_final,
                        'folder_name': nome_gdb,
                        'last_updated': str(data_raw),
                        'url': url_download,
                        'id': id_arquivo,
                        'checked_at': datetime.now().isoformat()
                    }, f, indent=4)
                print(f"\n🔔 SUCESSO! .env deve ficar: FILE_GDB={nome_gdb}")
                
                print("\n" + "="*60)
                print("🚀 ATUALIZANDO BANCO DE DADOS AUTOMATICAMENTE...")
                print("="*60)
                
                try:
                    print("\n1️⃣ Migrando nova base GDB para PostgreSQL...")
                    from migracao_db import migrar_gdb_para_sql
                    migrar_gdb_para_sql(limpar_antes=True)
                    
                    print("\n2️⃣ Reprocessando territórios Voronoi...")
                    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'modelos'))
                    from processar_voronoi import main as processar_voronoi
                    processar_voronoi()
                    
                    print("\n3️⃣ Regenerando análise de mercado e cache...")
                    from analise_mercado import analisar_mercado
                    analisar_mercado()
                    
                    print("\n" + "="*60)
                    print("✅ ATUALIZAÇÃO COMPLETA!")
                    print("="*60)
                    print("🎉 Nova base GDB integrada com sucesso!")
                    print("💾 Dados disponíveis no PostgreSQL")
                    print("🗺️ Voronoi atualizado")
                    print("📊 Cache regenerado")
                    print("="*60)
                    
                except Exception as e:
                    print(f"\n⚠️ AVISO: Erro ao atualizar banco automáticamente: {e}")
                    print("🛠️ Para atualizar manualmente, execute:")
                    print("  1. python src/etl/migracao_db.py")
                    print("  2. python src/modelos/processar_voronoi.py")
                    print("  3. python src/modelos/analise_mercado.py")

    except Exception as e:
        print(f"Erro: {e}")

if __name__ == "__main__":
    verificar_aneel()