# mis-finanzas
Para seguir mis finanzas y estados de cuenta, etc

Todo corre en la propia máquina. Los datos personales nunca salen de ella: lo único que la app
descarga, como máximo una vez por día, es información pública (la cotización del dólar MEP y
los paneles completos de precios del mercado).

## Requisitos

- [uv](https://docs.astral.sh/uv/) (instala Python 3.12 solo)
- Node 20 o más nuevo, y npm
- [just](https://just.systems/)

## Uso

```bash
just setup    # instala dependencias
just serve    # arma el frontend y abre la app en http://127.0.0.1:8000
just dev      # modo desarrollo: http://127.0.0.1:5173
```

La base de datos y los archivos importados se guardan en `~/.local/share/mis-finanzas`. Para
usar otra carpeta, ver `.env.example`.

Para usarla desde otros dispositivos (servidor en casa, Docker, contraseña y backups):
[docs/home-server.md](docs/home-server.md).

Diseño y decisiones: [docs/specs/2026-10-27-mis-finanzas-design.md](docs/specs/2026-10-27-mis-finanzas-design.md).
