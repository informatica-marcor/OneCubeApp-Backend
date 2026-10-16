# OneCubeApp Backend

API de gestión de accesos biométricos OneCube con FastAPI, SQLAlchemy, PostgreSQL, Alembic, Hikvision y Resend. Repositorio independiente extraído de `OneCube_Acceso_Biometrico/backend`, conservando `app/`, `alembic/` y sus dependencias. No necesita el monorepo ni los archivos del frontend.

## Configuración local

Se recomienda Python 3.12 (versión de la imagen Docker). La validación local se realizó con Python 3.14.6.

Desde la raíz del repositorio:

```sh
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

Ya se dejó un `.env` local con la conexión y claves vacías. Si se clona desde Git, copiar `.env.example` a `.env`. **No sobrescribir un entorno ya configurado.**

1. Pegar en `DATABASE_URL` la URL de PostgreSQL existente en Dokploy: `postgresql://usuario:password@host:puerto/base` (formato ilustrativo, no credenciales reales). Escapar caracteres especiales en usuario/password mediante URL encoding. Agregar opciones SSL si el servidor las requiere.
2. Recuperar `ENCRYPTION_KEY` del despliegue original: las credenciales de dispositivos almacenadas están cifradas con ella. **No generar una nueva clave para una base ya poblada.**
3. Recuperar `SECRET_KEY` del despliegue original para mantener tokens existentes, o generar otra si se acepta invalidarlos.
4. Configurar Resend (`RESEND_API_KEY`, `EMAIL_ADDRESS`) si se van a probar login por correo y notificaciones.
5. Mantener `ROOT=.` en local y `PUBLIC_BASE_URL=http://localhost:8000`; ajustar `CORS_ORIGINS` si el frontend usa otro origen.

Solo para una instalación nueva sin datos cifrados, generar Fernet:

```sh
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Para generar un secreto JWT nuevo:

```sh
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copiar las claves únicamente al `.env` local o a los secretos de Dokploy. Nunca al código ni a `.env.example`. `.env` y `.env.*` están excluidos de Git y Docker; únicamente la plantilla `.env.example` es versionable.

### Acceso a la base de Dokploy

El hostname interno de PostgreSQL en Dokploy normalmente solo es accesible desde su red Docker. Para pruebas desde tu PC, usar un endpoint alcanzable por VPN, túnel SSH o un puerto publicado de forma restringida; no exponer PostgreSQL a Internet sin controles de acceso. En producción conectar la API a la misma red de la base y usar su hostname interno.

**No se creó otra base ni se ejecutaron migraciones.** Antes de modificar una base existente, realizar un respaldo y revisar su estado:

```sh
alembic current
alembic heads
```

Solo aplicar `alembic upgrade head` después de revisar que corresponde y tener respaldo. El contenedor no lo ejecuta automáticamente.

### Ejecutar API

```sh
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Swagger: `http://localhost:8000/docs`. OpenAPI: `http://localhost:8000/openapi.json`.

## Variables principales

| Variable | Uso |
| --- | --- |
| `DATABASE_URL` | URL SQLAlchemy de PostgreSQL. También se admite `URL_DATABASE` por compatibilidad; `DATABASE_URL` no vacía tiene prioridad en API y Alembic. |
| `ENCRYPTION_KEY` | Clave Fernet original para cifrar/descifrar credenciales de dispositivos. |
| `SECRET_KEY`, `ALGORITHM` | Firma JWT; algoritmo predeterminado `HS256`. |
| `PUBLIC_BASE_URL` | URL pública de la API, por ejemplo `https://api.example.com`. Se usa para imágenes y adjuntos, sin agregar el puerto interno. |
| `CORS_ORIGINS` | Orígenes permitidos separados por coma, sin barra final. Incluir el dominio HTTPS exacto del frontend. Ya no se permiten todos los orígenes. |
| `ROOT` | Raíz de datos: `.` local, `/data` en Docker. Contiene `uploads/`, `logs/`, `assets/`. |
| `HOST`, `PORT` | Compatibilidad para construir URLs locales si no se define `PUBLIC_BASE_URL`; no cambian el puerto fijo 8000 del comando Docker. |
| `RESEND_API_KEY`, `EMAIL_ADDRESS` | Servicio y remitente de correo; necesarios para probar funciones de correo. |
| `TIMEZONE` | Predeterminada `America/Santiago`. |

La plantilla incluye también TTL de códigos, intentos y límites de acceso. Ninguna credencial de base de datos ni clave privada debe ir al repositorio frontend: sus variables `VITE_*` son públicas.

## Docker y Dokploy

Dockerfile multietapa con Python 3.12, compilación de psycopg2 contra libpq y ejecución sin root. Las variables se reciben en runtime, no se incorporan secretos en la imagen.

```sh
docker build -t onecube-backend .
# Prueba manual posterior, con .env completo:
docker run --rm --env-file .env -e ROOT=/data -p 8000:8000 -v onecube-data:/data onecube-backend
```

En Dokploy:

1. Publicar este repositorio backend por separado. La raíz contiene `Dockerfile`, `app/`, `alembic/` y `requirements.txt`; no usar el antiguo subdirectorio `/backend`.
2. Crear una **Application**, vincular el repositorio y elegir build **Dockerfile**, contexto raíz `.` (o directorio `/` en la interfaz), archivo `Dockerfile`.
3. Configurar las variables del `.env.example` en Environment/Secrets con valores reales. Usar `ROOT=/data`, `PUBLIC_BASE_URL=https://tu-dominio-api` y `CORS_ORIGINS=https://tu-dominio-frontend`. No dejar `ROOT=.` de la plantilla local en producción.
4. Conectar la aplicación a la red que permite llegar a PostgreSQL. No crear una segunda base.
5. Montar almacenamiento persistente en **`/data`** y asegurar permisos de escritura para UID/GID **10001**. Un volumen Docker nuevo suele tomar los permisos de la ruta de imagen; un bind mount requiere prepararlos manualmente.
6. Restaurar desde el despliegue anterior `uploads/` y, si existe, `assets/default_profile_photo.jpg` bajo `/data`. Estos archivos no estaban en el código original y no se pueden reconstruir desde Git. Revisar rutas absolutas antiguas guardadas en la BD antes de migrar almacenamiento; cambiar `ROOT` no reescribe esas rutas.
7. Configurar el dominio HTTPS y **puerto interno 8000**. Dokploy/Traefik termina TLS. El frontend usa este dominio como `VITE_API_URL` durante su compilación.
8. Desplegar y comprobar `/docs`, OpenAPI, login, adjuntos y fotos. Para un chequeo HTTP sin base se puede usar `/openapi.json`; esto no demuestra conectividad con PostgreSQL.

El backend requiere conectividad de red/VPN hacia dispositivos Hikvision. Desplegar en Dokploy no proporciona automáticamente acceso a la LAN de los equipos.

### Jobs de correo

Los módulos de `app/jobs/` se conservaron. No se añadieron tareas programadas ni se ejecutan automáticamente al iniciar Uvicorn. Si el despliegue anterior los ejecuta con cron, reproducir esa programación por separado usando la misma imagen, entorno y almacenamiento. Ejemplo de comando del worker: `python -m app.jobs.email_schedules_worker`. Puede enviar correos y modificar datos: no ejecutarlo contra producción como prueba casual.

## Estructura

```text
app/
  api/routers/    # Endpoints
  core/           # Configuración, seguridad, logging
  db/             # Sesiones SQLAlchemy
  models/         # Modelos
  services/       # Integraciones y negocio
  repositories/   # Acceso a datos
  jobs/           # Procesos de correo
  tests/          # Pruebas
alembic/          # Migraciones existentes
Dockerfile
.env.example     # Plantilla sin secretos
```

## Validación de la separación

- Dependencias originales instaladas sin modificaciones en `.venv` local; se instaló pytest solo como herramienta de validación.
- `python -m pytest -q app/tests/test_deployment_config.py`: **7 pruebas correctas** (precedencia/compatibilidad de URL, URL pública HTTPS, CORS y valores locales).
- `python -m compileall -q app alembic`: correcto.
- Smoke test con FastAPI TestClient: carga de aplicación, OpenAPI 200, preflight permitido 200 y origen no autorizado 400. Usó configuración temporal, sin conectar a PostgreSQL ni enviar correos.
- Suite heredada `app/tests/jobs/test_email_schedules_worker.py`: **25 correctas, 1 fallo**. Se reprodujo exactamente el mismo fallo en el original: `test_process_specific_date_marks_completed_with_errors_on_failure` espera `completed_with_errors` y obtiene `failed`. No se alteró esta lógica ajena a la separación.
- Git confirma exclusión de `.env`, `.env.production`, entorno virtual y archivos subidos. El repo destino ya existía independiente; no se hicieron commits ni branches.
- Docker no está instalado en este equipo; construcción y ejecución de la imagen pendientes de verificar en Dokploy o en un equipo con Docker.
- Prueba posterior de PostgreSQL en Dokploy: conexión y `SELECT 1` correctos en transacción de solo lectura. Las 10 tablas están presentes y coinciden en columnas, tipos, nulabilidad y claves primarias; no se compararon defaults, índices ni todas las restricciones.
- **Advertencia Alembic:** la base registra `0a910ab1ede5`, revisión ausente del historial local, cuyo head es `fccfc8d6990b`. Recuperar y comparar el historial del VPS antes de ejecutar migraciones. No usar `upgrade` ni `stamp` a ciegas.
- No se probaron login real, correos ni dispositivos; no se ejecutaron migraciones ni escrituras contra PostgreSQL.
