"""
Eventos de SQLAlchemy para hooks automáticos
"""

from app import db

def setup_events():
    """Configura todos los eventos de SQLAlchemy"""
    
    # Importar el modelo después de que db esté inicializado
    from app.models import Beneficiario
    
    @db.event.listens_for(Beneficiario, 'after_insert')
    def after_beneficiario_insert(mapper, connection, target):
        """Hook automático para crear carpeta después de insertar beneficiario"""
        try:
            from app.utils.beneficiario_utils import ensure_beneficiario_folder
            result = ensure_beneficiario_folder(target.id)
            if result['success']:
                print(f"✅ Carpeta del beneficiario creada automáticamente: {result['path']}")
            else:
                print(f"⚠️  Error creando carpeta automáticamente: {result['error']}")
        except Exception as e:
            print(f"⚠️  Error en hook after_insert: {e}")
    
    print("✅ Eventos de SQLAlchemy configurados") 