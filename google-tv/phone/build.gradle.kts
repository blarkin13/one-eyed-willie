// Yarr Media for Android phones: a separate app (its own package and launcher
// entry) built from the Google TV app's code and resources in ../app. The
// shared code checks AppKind.isTv(), so phone-only behaviour never reaches the TV.
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

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
    buildTypes {
        create("lean") {
            initWith(getByName("debug"))
            isDebuggable = false
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android.txt"), "../app/proguard-rules.pro")
            matchingFallbacks += "debug"
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
}
