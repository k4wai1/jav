plugins {
    id("com.android.application")
    kotlin("android")
    kotlin("plugin.serialization")
}

android {
    namespace = "dev.jev.jam"
    compileSdk = 34

    defaultConfig {
        applicationId = "dev.jev.jam"
        minSdk = 29
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"
    }

    buildTypes {
        debug {
            // Fase 0: sin minify en debug (R8 solo en release, ver AGENTS.md).
            isMinifyEnabled = false
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    // AGP 8.x no genera BuildConfig por defecto; JevLog lo necesita.
    buildFeatures {
        buildConfig = true
        // AIDL para el UserService de Shizuku (IShellService).
        aidl = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }

    // BouncyCastle repite metadatos en sus 3 jars (prov/pkix/util);
    // AGP exige excluir duplicados (fallos vistos en el primer build).
    packaging {
        resources {
            excludes += "META-INF/versions/9/OSGI-INF/MANIFEST.MF"
            excludes += "META-INF/LICENSE*"
            excludes += "META-INF/NOTICE*"
            excludes += "META-INF/*.SF"
            excludes += "META-INF/*.DSA"
            excludes += "META-INF/*.RSA"
        }
    }
}

dependencies {
    // Pins exactos: ARCHITECTURE.md §8. No añadir sin enmienda (AGENTS.md §4).
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("dev.rikka.shizuku:api:13.1.5")
    implementation("dev.rikka.shizuku:provider:13.1.5")
    implementation("org.java-websocket:Java-WebSocket:1.5.7")
    implementation("org.bouncycastle:bcprov-jdk18on:1.86")
    implementation("org.bouncycastle:bcpkix-jdk18on:1.86")

    // Tests JVM Fase 1 (recorrido, tope, snapshot_id). Sin Robolectric.
    testImplementation("junit:junit:4.13.2")
}
