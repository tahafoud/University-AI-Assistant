# Copy to android/app/proguard-rules.pro (needed only if you enable isMinifyEnabled).
-keep class ai.onnxruntime.** { *; }
-keep class com.microsoft.onnxruntime.** { *; }
-dontwarn ai.onnxruntime.**
