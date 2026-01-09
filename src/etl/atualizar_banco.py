"""
Script para atualizar completamente o banco de dados
Útil para executar manualmente ou em pipelines CI/CD
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def atualizar_banco_completo():
    """
    Executa todo o pipeline de atualização do banco de dados:
    1. Migra dados do GDB para PostgreSQL (limpando dados antigos)
    2. Processa territórios Voronoi
    3. Gera análise de mercado e cache
    """
    print("=" * 70)
    print("🔄 ATUALIZAÇÃO COMPLETA DO BANCO DE DADOS")
    print("=" * 70)
    
    try:
        print("\n📥 ETAPA 1/3: Migrando dados do GDB para PostgreSQL...")
        print("-" * 70)
        from etl.migracao_db import migrar_gdb_para_sql
        migrar_gdb_para_sql(limpar_antes=True)
        print("✅ Migração concluída!")
        
        print("\n🗺️  ETAPA 2/3: Processando territórios Voronoi...")
        print("-" * 70)
        from modelos.processar_voronoi import main as processar_voronoi
        processar_voronoi()
        print("✅ Voronoi processado!")
        
        print("\n📊 ETAPA 3/3: Gerando análise de mercado e cache...")
        print("-" * 70)
        from modelos.analise_mercado import analisar_mercado
        analisar_mercado()
        print("✅ Cache gerado!")
        
        print("\n" + "=" * 70)
        print("🎉 ATUALIZAÇÃO CONCLUÍDA COM SUCESSO!")
        print("=" * 70)
        print("\n📋 Resumo:")
        print("  ✅ Dados brutos migrados para PostgreSQL")
        print("  ✅ Territórios Voronoi calculados e salvos")
        print("  ✅ Cache de mercado gerado em JSONB")
        print("\n💡 Próximos passos:")
        print("  - API: python src/api.py")
        print("  - Dashboard: streamlit run src/dashboard.py")
        print("=" * 70)
        
        return True
        
    except Exception as e:
        print("\n" + "=" * 70)
        print("❌ ERRO NA ATUALIZAÇÃO")
        print("=" * 70)
        print(f"\n{type(e).__name__}: {e}")
        print("\n🛠️  Para depurar:")
        print("  1. Verifique se o banco PostgreSQL está rodando")
        print("  2. Verifique a variável DATABASE_URL no .env")
        print("  3. Execute cada etapa manualmente:")
        print("     - python src/etl/migracao_db.py")
        print("     - python src/modelos/processar_voronoi.py")
        print("     - python src/modelos/analise_mercado.py")
        print("=" * 70)
        
        import traceback
        traceback.print_exc()
        
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Atualiza banco de dados completo')
    parser.add_argument(
        '--skip-voronoi',
        action='store_true',
        help='Pula processamento de Voronoi (mais rápido)'
    )
    parser.add_argument(
        '--only-cache',
        action='store_true',
        help='Apenas regenera o cache (assume que dados já estão no banco)'
    )
    
    args = parser.parse_args()
    
    if args.only_cache:
        print("📊 Regenerando apenas cache...")
        from modelos.analise_mercado import analisar_mercado
        analisar_mercado()
    else:
        sucesso = atualizar_banco_completo()
        sys.exit(0 if sucesso else 1)
