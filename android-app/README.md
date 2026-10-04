# android-app — compañero headless de `jev-android-mcp`

App non-root (ver `../AGENTS.md`): expone percepción (AccessibilityService)
y ejecución (gestos + shell UID 2000 vía Shizuku) por WebSocket.
Fases 1–3 implementadas (dump_ui, WS, acciones + screenshot); la lógica
de shell con seguridad cerrada llega en Fase 6.

## Compilar (Debian 13, máquina pequeña)

Requisitos: JDK 17+ (probado con JDK 21), `ANDROID_HOME` apuntando a
`~/Android/Sdk` (ver `../docs/BUILD.md` para la instalación del toolchain).

```bash
cd android-app
./gradlew assembleDebug
# APK: app/build/outputs/apk/debug/app-debug.apk
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

`gradle.properties` está calibrado para 2 núcleos / ~2 GB RAM
(`-Xmx1024m`, sin daemon, sin paralelo, con build cache). No tocar sin medir.

## Estructura

```
app/src/main/
├── AndroidManifest.xml            # MainActivity + 2 servicios + ShizukuProvider
├── java/dev/jev/jam/
│   ├── MainActivity.kt            # onboarding (stub en Fase 0)
│   └── service/
│       ├── JevAccessibilityService.kt  # UI tree + gestos (Fase 1)
│       └── JevForegroundService.kt     # servidor WS (Fase 2)
└── res/{xml/accessibility_service_config.xml, values/strings.xml}
```

Contrato del socket: `../PROTOCOL.md`. Reglas: `../AGENTS.md`.
