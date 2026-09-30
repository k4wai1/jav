// Top-level build: plugin versions centralized here (apply false).
// Pins: ARCHITECTURE.md §8. AGP 8.5.2 + Gradle 8.7 + Kotlin 1.9.24.
plugins {
    id("com.android.application") version "8.5.2" apply false
    kotlin("android") version "1.9.24" apply false
    kotlin("plugin.serialization") version "1.9.24" apply false
}
