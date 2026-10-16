# 🐒 MonkeyGain

**MonkeyGain** es una aplicación de escritorio GTK 4 para analizar y escribir etiquetas ReplayGain mediante [`rsgain`](https://github.com/complexlogic/rsgain). Está diseñada como proyecto personal para Linux, especialmente elementary OS 8.1.

> Versión inicial **0.1.0**: primera implementación funcional del frontend. Antes de procesar una colección valiosa, prueba con una **copia** de un álbum y comprueba los resultados.

## Características

- Interfaz gráfica nativa GTK 4 con temas oscuro, claro o del sistema.
- Importar archivos sueltos o carpetas recursivamente.
- Análisis multiformato: FLAC, MP3, M4A (AAC/ALAC), Opus, Ogg, WAV, AIFF, WavPack, Monkey's Audio, MP2, MPC, TAK y WMA (dependiendo del backend y los códecs instalados).
- Cada carpeta se procesa por separado como un álbum; no mezcla álbumes distintos.
- Configuración de Album Gain, True Peak, loudness, clipping y peak máximo.
- Modo de solo análisis (`--tagmode=s`), sin escritura, o escritura de etiquetas (`--tagmode=i`).
- Confirmación antes de escribir etiquetas, registro de ejecución, exportación del registro y cancelación.
- Preferencias persistentes en `~/.config/monkeygain/settings.json` (no se suben a GitHub).
- Comandos ejecutados sin `shell=True`, con nombres de archivo seguros y rutas con espacios.

## Requisitos en elementary OS 8.1 / Ubuntu 24.04

```bash
sudo apt update
sudo apt install python3 python3-gi python3-gi-cairo gir1.2-gtk-4.0 rsgain
```

`rsgain` debe funcionar desde la terminal; confirma con `rsgain --version` y `rsgain custom --help`.

**No necesitas `pip install` ni un entorno virtual** para ejecutar la primera versión: utiliza los paquetes GTK/PyGObject instalados por el sistema.

## Ejecutar desde Visual Studio Code

Guarda el repositorio en `/data/Projects/MonkeyGain` y abre la carpeta completa:

```bash
mkdir -p /data/Projects
cd /data/Projects/MonkeyGain
code .
python3 run.py
```

También puedes lanzar `python3 run.py` desde la terminal integrada de VS Code o utilizar la configuración de depuración incluida en `.vscode/launch.json`.

## Uso

1. Pulsa **Archivos** para elegir pistas o **Carpeta** para importar recursivamente.
2. Revisa el listado: cada carpeta con audio pasa a ser un trabajo de álbum independiente.
3. Ajusta parámetros del panel lateral. Los valores predeterminados replican:

   ```bash
   rsgain custom --album --true-peak --loudness=-18 --clip-mode=p --max-peak=-1 --tagmode=i archivo1.flac archivo2.flac
   ```

4. Para probar **sin escribir metadatos**, desactiva *Escribir etiquetas* y haz clic en **Iniciar análisis**.
5. Si decides escribir etiquetas, la aplicación te pedirá confirmación. Usa copias para las primeras pruebas.
6. Revisa el registro y exporta el archivo de texto si necesitas auditar los resultados.

### Cómo se agrupan los álbumes

MonkeyGain **agrupa por directorio padre**, no leyendo las etiquetas ALBUM o ALBUMARTIST. Si tienes dos álbumes dentro de una misma carpeta, muévelos a carpetas separadas antes del análisis Album Gain. De la misma forma, los discos de un álbum repartidos en dos carpetas se analizan por separado en esta versión.

### Formatos de rsgain 3.4

La lista de extensiones admitidas por esta versión está alineada con [la documentación de rsgain v3.4](https://github.com/complexlogic/rsgain/blob/v3.4/README.md#supported-file-formats). **No** incluye DSF, WebM o Matroska porque rsgain agregó esos formatos en la versión 3.8.

El hecho de reconocer una extensión no garantiza que el decodificador correspondiente esté disponible en tu instalación de FFmpeg. El registro mostrará los errores que devuelva `rsgain`.

### Notas sobre ReplayGain

- `rsgain` escribe **metadatos de ganancia**, sin volver a codificar ni alterar las muestras de audio.
- El reproductor debe ser compatible con ReplayGain para usar estos valores en la reproducción.
- En Opus existen convenciones adicionales R128. Esta primera versión usa el comportamiento predeterminado de `rsgain 3.4` para Opus.
- Para valores numéricos detallados por pista y álbum, consulta la salida registrada por `rsgain`; la versión inicial no interpreta estos datos en una tabla estructurada.
- La barra de progreso mide **álbumes terminados**, no porcentaje exacto del tiempo de audio analizado.

## Probar el núcleo

```bash
python3 -m unittest discover -s tests -v
```

Estas pruebas no necesitan archivos musicales reales ni GTK.

## Estructura

```text
MonkeyGain/
├── monkeygain/
│   ├── __init__.py           # Versión y paquete
│   ├── core.py               # Agrupación, opciones y motor de análisis
│   └── app.py                # Interfaz GTK 4
├── assets/
│   ├── monkeygain.svg        # Icono del proyecto
│   └── style.css             # Apariencia claro/oscuro
├── tests/
│   └── test_core.py          # Pruebas del motor
├── .vscode/
│   ├── launch.json           # F5 para depurar
│   └── settings.json
├── .gitignore
├── LICENSE
└── run.py                   # Punto de entrada
```

## Publicar en GitHub

**Crea un repositorio vacío y público en GitHub llamado `MonkeyGain`**, sin inicializarlo con README ni `.gitignore` porque ya están aquí. Luego:

```bash
cd /data/Projects/MonkeyGain
git init
git add .
git commit -m "Initial release: MonkeyGain GTK frontend"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/MonkeyGain.git
git push -u origin main
```

Sustituye `TU_USUARIO` por tu usuario real de GitHub. La autenticación con HTTPS puede requerir token o Git Credential Manager; GitHub no admite contraseñas normales al hacer `push` por HTTPS.

## Próximas mejoras

- Arrastrar y soltar archivos en la ventana.
- Detalle estructurado de track gain, album gain y true peak.
- Separación de álbumes por metadatos; gestión de álbumes multidisco.
- Detección dinámica de formatos al actualizar `rsgain`.
- Integración con el lanzador de aplicaciones y empaquetado Flatpak / AppCenter.
- Mejor tratamiento de señales del proceso para cancelaciones forzadas.

## Licencia

El **código propio de MonkeyGain** se ofrece bajo licencia MIT (`LICENSE`). `rsgain`, GTK y las demás dependencias conservan sus respectivas licencias. Este proyecto es independiente y no está afiliado a los creadores de `rsgain` ni a elementary OS.
