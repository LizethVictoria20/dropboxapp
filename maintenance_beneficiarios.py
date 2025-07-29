#!/usr/bin/env python3
"""
Script de mantenimiento para garantizar que todos los beneficiarios tengan carpetas en Dropbox.
Se puede ejecutar manualmente o programar como tarea cron.
"""

import os
import sys
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Agregar el directorio actual al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.utils.beneficiario_utils import fix_all_beneficiarios, ensure_beneficiario_folder
from app.models import Beneficiario
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('maintenance_beneficiarios.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def main():
    """Función principal del script de mantenimiento"""
    print("🔧 Iniciando mantenimiento de beneficiarios...")
    logger.info("Iniciando mantenimiento de beneficiarios")
    
    app = create_app('production')
    
    with app.app_context():
        try:
            # Ejecutar corrección de todos los beneficiarios
            result = fix_all_beneficiarios()
            
            if result['success']:
                print(f"\n📊 Resumen del mantenimiento:")
                print(f"   Total de beneficiarios: {result['total']}")
                print(f"   ✅ Corregidos exitosamente: {result['fixed']}")
                print(f"   ❌ Errores encontrados: {result['errors']}")
                
                if result['errors'] > 0:
                    print(f"\n⚠️  Detalles de errores:")
                    for error in result['error_details']:
                        print(f"   - {error['beneficiario']}: {error['error']}")
                
                logger.info(f"Mantenimiento completado: {result['fixed']}/{result['total']} beneficiarios corregidos")
                
                # Si hay errores, intentar corregir específicamente
                if result['errors'] > 0:
                    print(f"\n🔄 Intentando corrección específica de beneficiarios con errores...")
                    retry_failed_beneficiarios()
                
            else:
                print(f"❌ Error en el mantenimiento: {result['error']}")
                logger.error(f"Error en mantenimiento: {result['error']}")
                
        except Exception as e:
            print(f"❌ Error general: {e}")
            logger.error(f"Error general en mantenimiento: {e}")
            import traceback
            traceback.print_exc()

def retry_failed_beneficiarios():
    """Reintenta corregir beneficiarios que fallaron"""
    try:
        beneficiarios = Beneficiario.query.all()
        
        for beneficiario in beneficiarios:
            # Verificar si el beneficiario tiene carpeta
            if not beneficiario.dropbox_folder_path:
                print(f"🔄 Reintentando corrección para: {beneficiario.nombre}")
                result = ensure_beneficiario_folder(beneficiario.id)
                
                if result['success']:
                    print(f"   ✅ Corregido: {result['path']}")
                else:
                    print(f"   ❌ Error: {result['error']}")
                    
    except Exception as e:
        print(f"❌ Error en reintento: {e}")
        logger.error(f"Error en reintento: {e}")

def check_specific_beneficiario(email):
    """Verifica y corrige un beneficiario específico"""
    print(f"🔍 Verificando beneficiario específico: {email}")
    
    app = create_app('production')
    
    with app.app_context():
        try:
            beneficiario = Beneficiario.query.filter_by(email=email).first()
            
            if not beneficiario:
                print(f"❌ Beneficiario {email} no encontrado")
                return
            
            print(f"✅ Beneficiario encontrado: {beneficiario.nombre} (ID: {beneficiario.id})")
            
            result = ensure_beneficiario_folder(beneficiario.id)
            
            if result['success']:
                print(f"✅ Carpeta verificada/corregida: {result['path']}")
            else:
                print(f"❌ Error: {result['error']}")
                
        except Exception as e:
            print(f"❌ Error verificando beneficiario: {e}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Mantenimiento de beneficiarios')
    parser.add_argument('--check', type=str, help='Verificar beneficiario específico por email')
    parser.add_argument('--retry', action='store_true', help='Reintentar corrección de fallidos')
    
    args = parser.parse_args()
    
    if args.check:
        check_specific_beneficiario(args.check)
    elif args.retry:
        retry_failed_beneficiarios()
    else:
        main() 