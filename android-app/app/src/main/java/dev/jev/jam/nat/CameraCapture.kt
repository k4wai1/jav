package dev.jev.jam.nat

import android.content.Context
import android.graphics.ImageFormat
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraDevice
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CaptureRequest
import android.media.ImageReader
import android.os.Handler
import android.os.HandlerThread
import android.util.Base64
import dev.jev.jam.socket.JamError
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * `take_photo` restringida (spec §11): Camera2 + JPEG + confirm siempre
 * (el gate vive en el dispatcher). Nunca silenciosa: requiere el FGS de
 * Jam vivo (notificación persistente) + indicador de plataforma.
 * En segundo plano sin FGS-cámara la plataforma lo deniega → error
 * honesto, nunca imagen inventada.
 */
object CameraCapture {

    private const val W = 1280
    private const val H = 720
    private const val MAX_B64 = 3_500_000

    fun capture(ctx: Context, which: String): String {
        NativeSensitive.checkCamera(ctx)
        val mgr = ctx.getSystemService(Context.CAMERA_SERVICE) as CameraManager
        val ids = try {
            mgr.cameraIdList
        } catch (t: Exception) {
            throw JamError("cámara no accesible: ${t.message?.take(120)}", "CAMERA_UNAVAILABLE")
        }
        if (ids.isEmpty()) throw JamError("sin cámaras", "CAMERA_UNAVAILABLE")
        val camId = when (which) {
            "front" -> ids.lastOrNull() ?: ids.first()
            else -> ids.first()
        }
        val thread = HandlerThread("jam-cam").also { it.start() }
        val handler = Handler(thread.looper)
        var device: CameraDevice? = null
        var session: CameraCaptureSession? = null
        var reader: ImageReader? = null
        try {
            val openLatch = CountDownLatch(1)
            var openError: Exception? = null
            try {
                mgr.openCamera(camId, object : CameraDevice.StateCallback() {
                    override fun onOpened(d: CameraDevice) {
                        device = d
                        openLatch.countDown()
                    }

                    override fun onDisconnected(d: CameraDevice) {
                        d.close()
                        openLatch.countDown()
                    }

                    override fun onError(d: CameraDevice, error: Int) {
                        openError = IllegalStateException("open error $error")
                        d.close()
                        openLatch.countDown()
                    }
                }, handler)
            } catch (t: SecurityException) {
                throw JamError("cámara denegada en este estado (FGS/permiso)", "CAMERA_DENIED")
            }
            if (!openLatch.await(10, TimeUnit.SECONDS)) {
                throw JamError("timeout abriendo cámara", "TIMEOUT")
            }
            openError?.let { throw JamError("apertura falló: ${it.message}", "CAMERA_FAILED") }
            val dev = device ?: throw JamError("cámara no abrió", "CAMERA_FAILED")

            val imgLatch = CountDownLatch(1)
            var jpeg: ByteArray? = null
            reader = ImageReader.newInstance(W, H, ImageFormat.JPEG, 2).apply {
                setOnImageAvailableListener({ r ->
                    r.acquireLatestImage()?.use { img ->
                        val buf = img.planes[0].buffer
                        val bytes = ByteArray(buf.remaining())
                        buf.get(bytes)
                        jpeg = bytes
                        imgLatch.countDown()
                    }
                }, handler)
            }
            val sessLatch = CountDownLatch(1)
            var sessError = false
            dev.createCaptureSession(
                listOf(reader.surface),
                object : CameraCaptureSession.StateCallback() {
                    override fun onConfigured(s: CameraCaptureSession) {
                        session = s
                        sessLatch.countDown()
                    }

                    override fun onConfigureFailed(s: CameraCaptureSession) {
                        sessError = true
                        sessLatch.countDown()
                    }
                },
                handler
            )
            if (!sessLatch.await(10, TimeUnit.SECONDS) || sessError) {
                throw JamError("sesión de captura falló", "CAMERA_FAILED")
            }
            val req = dev.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE)
                .apply { addTarget(reader.surface) }.build()
            session!!.capture(req, null, handler)
            if (!imgLatch.await(15, TimeUnit.SECONDS)) {
                throw JamError("timeout capturando", "TIMEOUT")
            }
            val bytes = jpeg ?: throw JamError("frame nulo", "CAMERA_FAILED")
            val b64 = Base64.encodeToString(bytes, Base64.NO_WRAP)
            if (b64.length > MAX_B64) {
                throw JamError(
                    "foto excede 4 MiB; reintenta (720p ya es el mínimo)",
                    "PAYLOAD_TOO_LARGE"
                )
            }
            return b64
        } catch (t: JamError) {
            throw t
        } catch (t: Exception) {
            throw JamError("captura falló: ${t.message?.take(150)}", "CAMERA_FAILED")
        } finally {
            try {
                session?.close()
            } catch (t: Throwable) {
                // Cierre best-effort.
            }
            try {
                device?.close()
            } catch (t: Throwable) {
                // Cierre best-effort.
            }
            try {
                reader?.close()
            } catch (t: Throwable) {
                // Cierre best-effort.
            }
            thread.quitSafely()
        }
    }

    fun resultW() = W
    fun resultH() = H
}

/** Respuesta JSON de `take_photo` (la arma el dispatcher). */
fun photoResult(b64: String) = buildJsonObject {
    put("img_base64", b64)
    put("w", CameraCapture.resultW())
    put("h", CameraCapture.resultH())
    put("via", "camera2")
}
