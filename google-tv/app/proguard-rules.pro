# Shrinking only: no obfuscation, so crash traces stay readable.
-dontobfuscate
-keepattributes *Annotation*,SourceFile,LineNumberTable
# The page talks to the app through this bridge; its methods are called by name.
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
