/bbalert
│   bbalert.py          <-- Ejecutable principal
│   requirements.txt    <-- Librerías necesarias
│   .env                <-- Token y Admins
│
├── core
│   ├── config.py       <-- Configuración central
│   └── database.py     <-- Gestión de JSON (Usuarios y Feeds)
│
├── services
│   ├── parser.py       <-- Tu FeedParserV4 (Limpio y optimizado)
│   └── monitor.py      <-- El bucle que revisa noticias
│
├── handlers
│   ├── conversation.py <-- Lógica de añadir Feeds/Canales/Plantillas
│   └── menus.py        <-- Botones y navegación
│
└── utils
    ├── logger.py       <-- Tu logger original
    └── common.py       <-- Funciones auxiliares (limpieza HTML, etc)