import java.io.FileInputStream
import java.util.Properties

// Signature des versions publiées : android/key.properties et le fichier de clé sont écrits par le flux GitHub
// à partir de ses secrets (jamais dans le dépôt). Sans eux, la clé de débogage (version de test locale).
val cleSignature = Properties().apply {
    val fichier = rootProject.file("key.properties")
    if (fichier.exists()) load(FileInputStream(fichier))
}

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "fr.climax.climax"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "fr.climax.climax"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        create("release") {
            if (!cleSignature.isEmpty) {
                storeFile = file(cleSignature.getProperty("storeFile"))
                storePassword = cleSignature.getProperty("storePassword")
                keyAlias = cleSignature.getProperty("keyAlias")
                keyPassword = cleSignature.getProperty("keyPassword")
                storeType = "pkcs12"
            }
        }
    }

    buildTypes {
        release {
            signingConfig = if (cleSignature.isEmpty) signingConfigs.getByName("debug")
                            else signingConfigs.getByName("release")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
