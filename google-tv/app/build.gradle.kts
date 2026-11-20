plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Permanent app signing key (create it once with create-signing-key.sh). CI
// passes it in YARR_KEYSTORE / YARR_KEYSTORE_PASSWORD so every build installs
// over the previous one and keeps the app's data (server, sign-in). Without
// them (local builds, forks) the usual per-machine debug key is used.
val yarrKeystore = System.getenv("YARR_KEYSTORE")?.let { file(it) }?.takeIf { it.isFile }

android {
    namespace = "studio.oneeyedwillie.tv"
    compileSdk = 36
    defaultConfig {
        applicationId = "studio.oneeyedwillie.tv"
        minSdk = 26
        targetSdk = 35
        versionCode = 8
        versionName = "0.1.7"
    }
    signingConfigs {
        if (yarrKeystore != null) create("yarr") {
            storeFile = yarrKeystore
            storePassword = System.getenv("YARR_KEYSTORE_PASSWORD")
            keyAlias = "yarr-media"
            keyPassword = System.getenv("YARR_KEYSTORE_PASSWORD")
        }
    }
    buildTypes {
        getByName("debug") {
            if (yarrKeystore != null) signingConfig = signingConfigs.getByName("yarr")
        }
        // Same app, stripped for the TV: not debuggable, unused code and
        // resources removed. Signed with the same key as the debug build, so
        // it installs the same way. "debug" stays traceable (OEWNav logcat).
        create("lean") {
            initWith(getByName("debug"))
            isDebuggable = false
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android.txt"), "proguard-rules.pro")
            matchingFallbacks += "debug"
            if (yarrKeystore != null) signingConfig = signingConfigs.getByName("yarr")
        }
    }
    sourceSets {
        // AppShell: a no-op here. The phone app (../phone) has the real one with
        // its native tab bar; the shared code calls it either way.
        getByName("main") { java.srcDirs("src/tvShell/java") }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}
dependencies {
    // ComponentActivity and OnBackPressedCallback are all the app takes from
    // AndroidX Activity; nothing uses Compose, Material3, tv-material or Coil.
    implementation("androidx.activity:activity:1.10.1")
    implementation("androidx.media3:media3-exoplayer:1.11.1")
    implementation("androidx.media3:media3-exoplayer-hls:1.11.1")
    implementation("androidx.media3:media3-ui:1.11.1")
    testImplementation("junit:junit:4.13.2")
}
