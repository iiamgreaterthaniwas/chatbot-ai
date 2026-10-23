plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// 签名信息由 GitHub Actions 通过环境变量传入，不写在代码里
val keystoreFile: String? = System.getenv("KEYSTORE_FILE")

android {
    namespace = "xyz.photoidmaker.dumplings"
    compileSdk = 34

    defaultConfig {
        applicationId = "xyz.photoidmaker.dumplings"
        minSdk = 24
        targetSdk = 34
        // 每次云端打包自动递增，手机才能覆盖安装新版本
        versionCode = (System.getenv("VERSION_CODE") ?: "1").toInt()
        versionName = System.getenv("VERSION_NAME") ?: "1.0.0"

        // App 打开的网址
        buildConfigField("String", "APP_URL", "\"https://dumplings.photoidmaker.xyz/\"")
    }

    signingConfigs {
        create("release") {
            if (keystoreFile != null) {
                storeFile = file(keystoreFile)
                storeType = System.getenv("KEYSTORE_TYPE") ?: "pkcs12"
                storePassword = System.getenv("KEYSTORE_PASSWORD")
                keyAlias = System.getenv("KEY_ALIAS")
                keyPassword = System.getenv("KEY_PASSWORD") ?: System.getenv("KEYSTORE_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // 没配置签名密钥时退回调试签名，只能用来试装，不能用来发布
            signingConfig = if (keystoreFile != null) signingConfigs.getByName("release") else signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        buildConfig = true
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.activity:activity-ktx:1.9.3")
}
