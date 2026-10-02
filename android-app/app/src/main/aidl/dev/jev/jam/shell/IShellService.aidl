package dev.jev.jam.shell;

interface IShellService {
    /** Ejecuta el comando; devuelve exit code. Salidas vía getStdout/getStderr. */
    int exec(in String[] cmd, in long timeoutMs);
    String getStdout();
    String getStderr();
}
