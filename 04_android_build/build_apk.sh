#!/usr/bin/env bash
# Build release APKs. Usage:
#   scripts/build_apk.sh https://your-host        # production API base
#   scripts/build_apk.sh                           # uses the default in app_config.dart
set -euo pipefail
cd "$(dirname "$0")/.."

API_BASE="${1:-}"

command -v flutter >/dev/null || { echo "ERROR: flutter not found in PATH"; exit 1; }

# 1) The model files must be bundled, otherwise the app silently runs without the AI.
for f in intent_model.onnx vocab.json labels.json config.json; do
  [ -f "assets/model/$f" ] || { echo "ERROR: assets/model/$f is missing (copy from university_nlu/artifacts)"; exit 1; }
done

echo ">> pub get"
flutter pub get

echo ">> tests (Dart vs Python normalizer parity)"
flutter test

DEFINES=()
if [ -n "$API_BASE" ]; then DEFINES+=("--dart-define=API_BASE=$API_BASE"); fi

echo ">> building release APKs (one per CPU architecture)"
flutter build apk --release --split-per-abi "${DEFINES[@]}"

OUT=build/app/outputs/flutter-apk
mkdir -p dist
cp "$OUT"/app-*-release.apk dist/
echo
echo ">> done. Files in ./dist :"
ls -lh dist/*.apk
echo
if command -v sha256sum >/dev/null; then sha256sum dist/*.apk; fi
echo
echo "Most modern phones: app-arm64-v8a-release.apk"
