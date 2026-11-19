plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "studio.oneeyedwillie.tv"
    compileSdk = 36
    defaultConfig {
        applicationId = "studio.oneeyedwillie.tv"
        minSdk = 26
        targetSdk = 35
        versionCode = 5
        versionName = "0.1.4"
    }
    buildTypes {
        // Same app, stripped for the TV: not debuggable, unused code and
        // resources removed. Signed with the debug key like the debug build, so
        // it installs the same way. "debug" stays traceable (OEWNav logcat).
        create("lean") {
            initWith(getByName("debug"))
            isDebuggable = false
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android.txt"), "proguard-rules.pro")
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
    // ComponentActivity and OnBackPressedCallback are all the app takes from
    // AndroidX Activity; nothing uses Compose, Material3, tv-material or Coil.
    implementation("androidx.activity:activity:1.10.1")
    implementation("androidx.media3:media3-exoplayer:1.11.1")
    implementation("androidx.media3:media3-exoplayer-hls:1.11.1")
    implementation("androidx.media3:media3-ui:1.11.1")
    testImplementation("junit:junit:4.13.2")
}
