# University AI Chat (Flutter) - Phase 3

## Setup
1. `flutter create university_ai_chat` (any folder), then copy this project's
   `lib/`, `assets/`, `test/` and `pubspec.yaml` over the generated ones.
2. Copy from `university_nlu/artifacts/` into `assets/model/`:
   `intent_model.onnx` (or the int8 file renamed), `vocab.json`, `labels.json`,
   `config.json`, `golden_tests.json`.
3. Android: in `android/app/src/main/AndroidManifest.xml` add
   `<uses-permission android:name="android.permission.INTERNET"/>` (release builds
   need it) and, for HTTP testing only, `android:usesCleartextTraffic="true"` on
   `<application>`. If the build complains, set `minSdk 24` in `android/app/build.gradle`.
4. Serve the Python output (announcements.json + media/):
   `cd university_ingest/data && python -m http.server 8000`
   Emulator reaches it at http://10.0.2.2:8000 (default). Real device / production:
   `flutter run --dart-define=API_BASE=https://your-host`
5. `flutter pub get && flutter test && flutter run`
