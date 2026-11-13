# المرحلة 4: بناء ملف APK

## 0) المتطلبات (مرة واحدة)
- Flutter SDK + Android Studio (أو Android command-line tools) + JDK 17.
- `flutter doctor` يجب أن يظهر Android toolchain بعلامة صح. إن طلب التراخيص: `flutter doctor --android-licenses`.
- ملفات النموذج داخل `assets/model/` (من `university_nlu/artifacts/`).

## 1) تجهيز مشروع أندرويد (مرة واحدة)
بعد `flutter create` ونسخ ملفات المشروع (انظر README_PHASE3.md):
1. **الأذونات**: أضف `INTERNET` من `android_templates/AndroidManifest.snippet.xml`.
   نسخة release لا تتضمنه تلقائياً، فالمزامنة تعمل في وضع التطوير وتفشل بصمت في الـAPK.
2. **أمان الشبكة**: انسخ `res_xml/network_security_config.xml` إلى `android/app/src/main/res/xml/`.
   افتراضياً HTTPS فقط. لسيرفر تجريبي HTTP فعّل مقطع `domain-config` ثم احذفه في النسخة النهائية.
3. **الهوية والإصدار الأدنى**: ادمج `build.gradle.kts.snippet` في `android/app/build.gradle.kts`
   (غيّر `applicationId`، واجعل `minSdk = 24`).

## 2) أسرع طريق لنسخة تجريبية
```bash
scripts/build_apk.sh https://your-host      # Windows: .\scripts\build_apk.ps1 -ApiBase https://your-host
```
السكربت يتحقق من وجود ملفات النموذج، ثم يشغّل الاختبارات، ثم يبني APK منفصلاً لكل معمارية ويضعها في `dist/`.
بدون عنوان سيرفر يستخدم الافتراضي في `app_config.dart` (`10.0.2.2`، للمحاكي فقط).

يدوياً:
```bash
flutter pub get
flutter test
flutter build apk --release --split-per-abi --dart-define=API_BASE=https://your-host
# الناتج: build/app/outputs/flutter-apk/app-arm64-v8a-release.apk
```

**أي ملف أختار؟** `arm64-v8a` يناسب معظم الهواتف الحديثة. للتأكد من هاتف معيّن:
`adb shell getprop ro.product.cpu.abi`. وبناء `--split-per-abi` مهم لأن مكتبات onnxruntime
الأصلية تضخّم الـAPK الشامل كثيراً. لملف واحد صغير لمعظم الأجهزة:
`flutter build apk --release --target-platform android-arm64`.

## 3) التثبيت
- USB: `adb install -r dist/app-arm64-v8a-release.apk`
- أو أرسل الملف للهاتف وفعّل "التثبيت من مصادر غير معروفة" لتطبيق المتصفح/الملفات.

## 4) توقيع النسخة النهائية (قبل توزيعها على الطلاب)
قالب gradle أعلاه يوقّع بمفتاح debug إن لم يوجد `key.properties`. هذا مقبول للتجربة فقط.
للتوزيع:
```bash
keytool -genkey -v -keystore ~/upload-keystore.jks -storetype JKS \
        -keyalg RSA -keysize 2048 -validity 10000 -alias upload
cp android_templates/key.properties.example android/key.properties   # عبّئ القيم
```
- **احتفظ بنسخة احتياطية من ملف `.jks` وكلمات سره.** فقدانه يعني استحالة نشر تحديثات لنفس التطبيق.
- لا ترفع `key.properties` ولا `.jks` إلى Git (`gitignore.snippet`).
- لمتجر Google Play يلزم `flutter build appbundle --release` بدل APK.

## 5) اختبار قبل التسليم (مهم)
1. شغّل `flutter run --release` على **هاتف حقيقي**، فبعض المشاكل لا تظهر إلا في release.
2. أنشئ حساباً، واسأل: "متى الامتحانات النهائية؟" وتأكد أن الرد صحيح (النموذج يعمل).
3. فعّل وضع الطيران وأعد فتح التطبيق: يجب أن تظهر المحادثات والإعلانات المحفوظة.
4. أطفئ الوضع، واسحب للتحديث في تبويب الإعلانات: يجب أن تصل إعلانات جديدة.
5. بدّل حساباً ثانياً وتأكد أن المحادثات لا تظهر له.
6. عند أي انهيار: `adb logcat | grep -i -E "flutter|onnx|AndroidRuntime"`.

## 6) أعطال متوقعة
| العرَض | السبب والحل |
|---|---|
| المزامنة تعمل بالتطوير وتفشل بالـAPK | نسيان إذن `INTERNET`، أو سيرفر HTTP بدون استثناء في network_security_config |
| يعمل بالتطوير وينهار في release | فعّلت minify: عطّله أولاً، ثم أضف `proguard-rules.pro` |
| البوت يردّ دائماً "لم أفهم سؤالك" | النموذج لم يُحمَّل (ملفات ناقصة في assets/model)، راجع logcat |
| ردود النموذج غريبة فقط على الهاتف | عدم تطابق التطبيع: شغّل اختبار parity وقارن `golden_tests.json` |
| `minSdkVersion ... cannot be smaller than` | ارفع `minSdk` إلى 24 |
| فشل Gradle (JDK/AGP) | استخدم JDK 17، ثم `flutter clean && flutter pub get` |
| APK ضخم | استخدم `--split-per-abi` أو `--target-platform android-arm64`، ونسخة int8 من النموذج |
