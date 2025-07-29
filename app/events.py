"""
Eventos de SQLAlchemy para hooks automáticos
"""

from app import db

def setup_events():
    """Configura todos los eventos de SQLAlchemy"""
    
    # Importar el modelo después de que db esté inicializado
    from app.models import Beneficiario
    
    
    print("✅ Eventos de SQLAlchemy configurados") 