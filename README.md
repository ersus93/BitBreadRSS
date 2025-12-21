# 🤖 BitBread RSS Bot

BitBread es un bot de Telegram robusto y asíncrono diseñado para gestionar feeds RSS y automatizar el envío de noticias a canales de Telegram con un formato elegante y profesional.

## ✨ Características

* **🔍 Resolución Automática de Feeds**: Capacidad para encontrar automáticamente la URL del RSS simplemente enviando el enlace de un sitio web.
* **🛡️ Bypass de WAF/Cloudflare**: Utiliza `curl_cffi` para emular navegadores reales y evitar bloqueos comunes en sitios protegidos.
* **🖼️ Extracción Inteligente de Imágenes**: Analiza el contenido de los artículos para extraer la mejor imagen disponible para las vistas previas.
* **⚡ Soporte para Instant View**: Genera enlaces de *Instant View* automáticamente usando plantillas (rhashes) globales o personalizadas por el usuario.
* **📊 Base de Datos Asíncrona**: Sistema de almacenamiento en JSON con escritura atómica y semáforos para garantizar la integridad de los datos en entornos concurrentes.
* **🎨 Formatos Personalizables**: Elige entre un estilo visual con foto o un estilo de texto minimalista para tus mensajes.
* **⚙️ Gestión Multiusuario**: Menús interactivos mediante botones inline para configurar intervalos de actualización, eliminar canales o probar feeds.

## 📂 Estructura del Proyecto

```text
├── bbalert.py            # Punto de entrada del bot
├── core/
│   ├── config.py         # Configuraciones y constantes
│   └── database.py       # Lógica de persistencia de datos
├── handlers/
│   ├── conversation.py   # Flujos de configuración paso a paso
│   └── menus.py          # Menús interactivos y botones
├── services/
│   ├── iv_generator.py   # Motor de Instant View
│   ├── monitor.py        # Bucle de vigilancia de feeds
│   ├── parser.py         # Extracción y limpieza de datos RSS
│   └── resolver.py       # Descubrimiento de feeds ocultos
└── utils/
    ├── common.py         # Funciones de limpieza de HTML y texto
    └── logger.py         # Sistema de logs con rotación

```

## 🛠️ Instalación

1. **Clonar el repositorio**:
```bash
git clone [https://github.com/tu-usuario/bitbread-rss-bot.git](https://github.com/tu-usuario/bitbread-rss-bot.git)
cd bitbread-rss-bot

```


2. **Instalar dependencias**:
```bash
pip install -r requirements.txt

```


*Dependencias clave: `python-telegram-bot`, `feedparser`, `curl_cffi`, `beautifulsoup4`.*
3. **Configuración**:
Crea un archivo de configuración (o variables de entorno) con tu `BOT_TOKEN` obtenido de [@BotFather](https://t.me/BotFather).
4. **Ejecutar**:
```bash
python bbalert.py

```



## 🚀 Uso

1. Inicia el bot con `/start`.
2. **Añadir Canal**: Haz admin al bot en tu canal de Telegram y envíale el ID o reenvía un mensaje del canal al bot.
3. **Añadir Feed**: Envía la URL de cualquier sitio web; el bot intentará localizar el feed RSS por ti.
4. **Personalizar**: Desde el menú "Mis Feeds", configura el intervalo de actualización o el estilo de publicación.

## 📝 Licencia

Este proyecto está bajo la Licencia **MIT**. Consulta el archivo `LICENSE` para más detalles.

---

*Desarrollado con ❤️ para la comunidad de Telegram.*

