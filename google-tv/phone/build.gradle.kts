// Yarr Media for Android phones: a separate app (its own package and launcher
// entry) built from the Google TV app's code and resources in ../app. The
// shared code checks AppKind.isTv(), so phone-only behaviour never reaches the TV.
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
    // Same namespace as the TV app so the shared code's R and imports resolve.
    namespace = "studio.oneeyedwillie.tv"
    compileSdk = 36
    defaultConfig {
        applicationId = "media.yarr.android"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
    }
    sourceSets {
        getByName("main") {
            java.srcDirs("../app/src/main/java")
            res.srcDirs("../app/src/main/res")
            manifest.srcFile("src/main/AndroidManifest.xml")
        }
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
        create("lean") {
            initWith(getByName("debug"))
            isDebuggable = false
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android.txt"), "../app/proguard-rules.pro")
            matchingFallbacks += "debug"
            if (yarrKeystore != null) signingConfig = signingConfigs.getByName("yarr")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}
dependencies {
    implementation("androidx.activity:activity:1.10.1")
    implementation("androidx.media3:media3-exoplayer:1.11.1")
    implementation("androidx.media3:media3-exoplayer-hls:1.11.1")
    implementation("androidx.media3:media3-ui:1.11.1")
    // Phone-only (the TV app doesn't include these): app styling injected at
    // document start, and pull to refresh.
    implementation("androidx.webkit:webkit:1.12.1")
    implementation("androidx.swiperefreshlayout:swiperefreshlayout:1.1.0")
    // ServiceCompat (foreground service types) for downloads.
    implementation("androidx.core:core:1.13.1")
}
