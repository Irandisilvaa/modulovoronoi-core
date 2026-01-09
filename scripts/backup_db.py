
import os
import subprocess
from datetime import datetime
import sys

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def backup_db():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = "backups"
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
        
    filename = f"{backup_dir}/backup_gridscope_{timestamp}.sql"
    
    cmd = f"docker-compose exec -T gridscope_db pg_dump -U gridscope_user gridscope_db > {filename}"
    
    print(f"📦 Iniciando backup: {filename}")
    try:
        subprocess.run(cmd, shell=True, check=True)
        print(f"✅ Backup concluído com sucesso!")
        
        list_backups = sorted([f for f in os.listdir(backup_dir) if f.endswith('.sql')])
        while len(list_backups) > 5:
            oldest = list_backups.pop(0)
            os.remove(os.path.join(backup_dir, oldest))
            print(f"♻️ Removido backup antigo: {oldest}")
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Erro ao realizar backup: {e}")

if __name__ == "__main__":
    backup_db()
