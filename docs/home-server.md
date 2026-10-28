# Usar mis-finanzas desde otros dispositivos

La app guarda todo en una carpeta de la máquina donde corre. Para verla desde el celular u otra
computadora, la dejás corriendo en una máquina de la casa y entrás por **Tailscale**: una red
privada entre tus dispositivos, cifrada. **Nunca abras un puerto en el router**: la app quedaría
expuesta a internet.

## 1. Contraseña

Mientras la app escuche solo en `127.0.0.1`, no pide contraseña. Para escuchar en cualquier otra
dirección (como hace Docker) primero hay que poner una; si no, **la app no arranca**.

```bash
just password                                   # sin Docker
docker compose run --rm app mis-finanzas-password   # con Docker
```

Pide la contraseña dos veces (al menos 12 caracteres) y guarda solo un hash en la carpeta de
datos (`auth.json`). Cambiarla cierra la sesión en todos los navegadores. Después de 5
contraseñas incorrectas, el ingreso se bloquea por hasta 15 minutos.

## 2. Con Docker

En la máquina que hace de servidor, desde la carpeta del repo:

```bash
mkdir -p data backups
docker compose run --rm app mis-finanzas-password
docker compose up -d --build
docker compose ps        # "healthy" cuando está lista
```

- Los datos quedan en `./data` y los backups en `./backups`. Para guardarlos en otro disco:
  `MIS_FINANZAS_BACKUP_PATH=/mnt/otro-disco/mis-finanzas docker compose up -d`.
- La imagen corre con el usuario de UID 1000: las carpetas `data` y `backups` tienen que ser
  de ese usuario (lo son si las creó tu usuario, en la mayoría de las instalaciones).
- El puerto se publica solo en `127.0.0.1:8000`: desde otras máquinas se entra por Tailscale.
- Para actualizar: `git pull && docker compose up -d --build`. La base se actualiza sola al
  arrancar.

Sin Docker: `MIS_FINANZAS_BACKUP_DIR=... just serve`, con las variables de `.env.example`.

## 3. Tailscale

1. Instalá Tailscale en el servidor y en cada dispositivo, con la misma cuenta
   (<https://tailscale.com/download>).
2. En el servidor:

   ```bash
   sudo tailscale serve --bg 8000
   ```

   Eso publica la app **solo dentro de tu red de Tailscale**, con HTTPS, en
   `https://<nombre-del-servidor>.<tu-tailnet>.ts.net`. `tailscale serve status` muestra la
   dirección.
3. Abrí esa dirección desde el celular y entrá con la contraseña.

El `compose.yaml` marca la cookie de sesión como segura (`MIS_FINANZAS_COOKIE_SECURE=true`):
el navegador solo la manda por HTTPS, que es lo que da `tailscale serve`. Con Tailscale no se
abre ningún puerto en el router. No uses `tailscale funnel`: eso sí publica la app en
internet.

Con WireGuard propio también funciona: dejá el puerto en `127.0.0.1` y poné delante un proxy
con HTTPS que escuche solo en la interfaz de WireGuard.

## 4. Backups

Con `MIS_FINANZAS_BACKUP_DIR` definido (Docker lo define), la app hace un backup por día:

- `db/finanzas-AAAA-MM-DD.db`: una copia consistente de la base, aunque la app esté
  escribiendo. Se guardan los últimos 14 días (`MIS_FINANZAS_BACKUP_KEEP_DAYS`).
- `uploads/`: los archivos originales importados, cada uno copiado una vez.

Un backup en el mismo disco no sirve si el disco se rompe: apuntá la carpeta a otro disco, o
sincronizala fuera de la máquina. Para hacer uno en el momento: `just backup [carpeta]`, o
`docker compose exec app python -m mis_finanzas.tools.backup`.

Para restaurar: con la app detenida, copiá el `.db` elegido a `data/finanzas.db` y el
contenido de `uploads/` a `data/uploads/`.

La contraseña (`auth.json`) no entra en el backup, a propósito: después de restaurar,
volvé a ponerla con el paso 1.
