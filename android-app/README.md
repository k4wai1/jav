# android-app — compañero headless de `Jav`

App non-root (ver `../AGENTS.md`): expone percepción (AccessibilityService)
y ejecución (gestos + shell UID 2000 vía Shizuku) por WebSocket. Paquete
`dev.k4wai1.jav` (label `Jav`). Estado actual:

- **Loopback WS `127.0.0.1:38472`** (token bearer obligatorio, single-client).
- **WSS en la IP tailnet** (`100.64.0.0/10`, nunca `0.0.0.0`): cert X.509v3
  autofirmado `CN=jav.local` (BC local, PKCS#12 cifrado en `filesDir`) y
  **token AES-GCM/256 en `AndroidKeyStore`** (`ws_token_enc`); lockout 5
  fallos/60 s → 5 min.
- **Audit ring 500** + Kill Switch (notificación + Quick Settings tile).
- **`shell` con seguridad cerrada** (denylist de irreversibles + grant
  interactivo `1 cmd`/`5 min`/`30 min`; N2 vivo).
- v5 director-client: `set_clipboard {text}` → `{chars}` vía
  `ClipboardManager.setPrimaryClip` por la propia app (sin Shizuku, sin
  grant, scope `ui`); la lectura sigue por host `dumpsys`.

Kotlin **88/88** en verde (`:app:testDebugUnitTest`).

## Compilar (Debian 13, máquina pequeña)

Requisitos: JDK 17+ (probado con JDK 21), `ANDROID_HOME` apuntando a
`~/Android/Sdk` (ver `../docs/BUILD.md`).

```bash
cd android-app
./gradlew clean :app:testDebugUnitTest :app:assembleDebug --offline
# APK: app/build/outputs/apk/debug/app-debug.apk
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

`gradle.properties` está calibrado para 2 núcleos / ~2 GB RAM
(`-Xmx1024m`, sin daemon, sin paralelo, con build cache). No tocar sin medir.

## Estructura

```
app/src/main/
├── AndroidManifest.xml                 # MainActivity + servicios + ShizukuProvider
├── aidl/dev/k4wai1/jav/shell/IShellService.aidl
├── java/dev/k4wai1/jav/
│   ├── MainActivity.kt                 # onboarding (estado Shizuku/tailnet/cert)
│   ├── service/                        # JevAccessibilityService, JevForegroundService,
│   │                                   # JamKillSwitchTile, JamNotificationListener
│   ├── socket/                         # JamWsServer, CommandDispatcher, AuditLog,
│   │                                   # AuthStore, AuthLockout, TlsCertStore, WsProtocol
│   ├── net/TailnetDetector.kt
│   ├── shell/                          # ShellPolicy, ShellGrantManager, ShizukuBridge
│   ├── nat/                            # providers nativos N0/N1
│   └── ui/
└── res/{xml/accessibility_service_config.xml, values/strings.xml}
```

Contrato del socket: `../PROTOCOL.md`. Reglas: `../AGENTS.md`.
