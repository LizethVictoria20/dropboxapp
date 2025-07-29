#!/usr/bin/env python3
"""
Script específico para corregir el beneficiario benito@gmail.com
"""

import os
import sys
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Agregar el directorio actual al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User, Beneficiario
from app.dropbox_utils import create_dropbox_folder
import dropbox

def fix_beneficiario_benito():
    """Corrige específicamente el beneficiario benito@gmail.com"""
    print("🔧 Corrigiendo beneficiario benito@gmail.com")
    print("=" * 45)
    
    app = create_app('production')
    
    with app.app_context():
        try:
            # Verificar configuración de Dropbox
            api_key = app.config.get("DROPBOX_API_KEY")
            if not api_key:
                print("❌ DROPBOX_API_KEY no está configurada")
                return False
            
            # Conectar a Dropbox
            dbx = dropbox.Dropbox(api_key)
            account = dbx.users_get_current_account()
            print(f"✅ Conectado a Dropbox como: {account.email}")
            
            # Buscar el beneficiario benito
            benito = Beneficiario.query.filter_by(email="benito@gmail.com").first()
            if not benito:
                print("❌ No se encontró el beneficiario benito@gmail.com")
                return False
            
            print(f"✅ Beneficiario encontrado: {benito.nombre} (ID: {benito.id})")
            
            # Verificar el titular
            if not benito.titular:
                print("❌ El beneficiario no tiene titular asociado")
                return False
            
            titular = benito.titular
            print(f"📁 Titular: {titular.email} (ID: {titular.id})")
            
            # Verificar que el titular tenga carpeta
            if not titular.dropbox_folder_path:
                print("⚠️  El titular no tiene carpeta, creando...")
                try:
                    titular.dropbox_folder_path = f"/{titular.email}"
                    create_dropbox_folder(titular.dropbox_folder_path)
                    db.session.commit()
                    print(f"✅ Carpeta del titular creada: {titular.dropbox_folder_path}")
                except Exception as e:
                    print(f"❌ Error creando carpeta del titular: {e}")
                    return False
            else:
                print(f"✅ Titular ya tiene carpeta: {titular.dropbox_folder_path}")
            
            # Verificar si benito tiene carpeta
            if not benito.dropbox_folder_path:
                print("⚠️  Benito no tiene carpeta, creando...")
                try:
                    path_ben = f"{titular.dropbox_folder_path}/{benito.nombre}_{benito.id}"
                    create_dropbox_folder(path_ben)
                    benito.dropbox_folder_path = path_ben
                    db.session.commit()
                    print(f"✅ Carpeta de Benito creada: {path_ben}")
                except Exception as e:
                    print(f"❌ Error creando carpeta de Benito: {e}")
                    return False
            else:
                print(f"✅ Benito ya tiene carpeta configurada: {benito.dropbox_folder_path}")
                
                # Verificar que la carpeta existe en Dropbox
                try:
                    metadata = dbx.files_get_metadata(benito.dropbox_folder_path)
                    print(f"✅ Carpeta existe en Dropbox: {metadata.name}")
                except dropbox.exceptions.ApiError as e:
                    if "not_found" in str(e):
                        print("⚠️  Carpeta no existe en Dropbox, recreando...")
                        try:
                            create_dropbox_folder(benito.dropbox_folder_path)
                            print(f"✅ Carpeta recreada: {benito.dropbox_folder_path}")
                        except Exception as create_error:
                            print(f"❌ Error recreando carpeta: {create_error}")
                            return False
                    else:
                        print(f"❌ Error verificando carpeta: {e}")
                        return False
            
            # Verificación final
            print("\n🔍 Verificación final:")
            print(f"   Beneficiario: {benito.nombre} ({benito.email})")
            print(f"   Titular: {titular.email}")
            print(f"   Carpeta del titular: {titular.dropbox_folder_path}")
            print(f"   Carpeta del beneficiario: {benito.dropbox_folder_path}")
            
            # Verificar que ambas carpetas existen
            try:
                titular_metadata = dbx.files_get_metadata(titular.dropbox_folder_path)
                benito_metadata = dbx.files_get_metadata(benito.dropbox_folder_path)
                print("✅ Ambas carpetas existen en Dropbox")
                print(f"   Titular: {titular_metadata.name}")
                print(f"   Benito: {benito_metadata.name}")
            except Exception as e:
                print(f"❌ Error en verificación final: {e}")
                return False
            
            print("\n🎉 ¡Benito corregido exitosamente!")
            return True
            
        except Exception as e:
            print(f"❌ Error general: {e}")
            import traceback
            traceback.print_exc()
            return False

def listar_todos_beneficiarios():
    """Lista todos los beneficiarios para verificar el estado"""
    print("\n📋 Estado de todos los beneficiarios:")
    print("=" * 40)
    
    app = create_app('production')
    
    with app.app_context():
        try:
            beneficiarios = Beneficiario.query.all()
            
            if not beneficiarios:
                print("No hay beneficiarios en la base de datos")
                return
            
            for ben in beneficiarios:
                print(f"\n👤 {ben.nombre} ({ben.email})")
                print(f"   ID: {ben.id}")
                print(f"   Titular: {ben.titular.email if ben.titular else 'Sin titular'}")
                print(f"   Carpeta: {ben.dropbox_folder_path or 'No configurada'}")
                
                # Verificar estado de la carpeta
                if ben.dropbox_folder_path:
                    try:
                        dbx = dropbox.Dropbox(app.config["DROPBOX_API_KEY"])
                        metadata = dbx.files_get_metadata(ben.dropbox_folder_path)
                        print(f"   Estado: ✅ Existe en Dropbox")
                    except dropbox.exceptions.ApiError as e:
                        if "not_found" in str(e):
                            print(f"   Estado: ❌ No existe en Dropbox")
                        else:
                            print(f"   Estado: ⚠️  Error verificando: {e}")
                else:
                    print(f"   Estado: ⚠️  Sin carpeta configurada")
                    
        except Exception as e:
            print(f"❌ Error listando beneficiarios: {e}")

if __name__ == "__main__":
    print("🚀 Iniciando corrección de Benito...")
    
    # Ejecutar corrección específica
    success = fix_beneficiario_benito()
    
    if success:
        # Listar todos los beneficiarios
        listar_todos_beneficiarios()
        
        print("\n✅ Proceso completado!")
        print("📝 Próximos pasos:")
        print("   1. Verifica en Dropbox que la carpeta de Benito se creó")
        print("   2. Intenta crear un nuevo beneficiario desde la web")
        print("   3. Verifica que los archivos se pueden subir a la carpeta de Benito")
    else:
        print("\n❌ Se encontraron problemas durante la corrección")
        print("   Revisa los errores anteriores para identificar el problema") 