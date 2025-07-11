# MyDropboxApp (estructura básica)

## Requisitos
- Python 3.8+
- PostgreSQL
- Dropbox API key

## Instalación
1. Clona este repo y crea un entorno virtual.
2. Instala dependencias:
    ```
    pip install -r requirements.txt
    ```
3. Copia `.env.example` a `.env` y edítalo.
4. Crea tu BD PostgreSQL y migra:
    ```
    flask db init
    flask db migrate
    flask db upgrade
    ```
5. Corre la app:
    ```
    flask run
    ```

## Uso
- Crea usuarios y automáticamente tendrás carpetas en Dropbox y en la base de datos.

## Notas
- Asegúrate de tu API KEY de Dropbox en el `.env`
- Amplía las rutas según lo que necesites (mover, eliminar, renombrar, etc.)
