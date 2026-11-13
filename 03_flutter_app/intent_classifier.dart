import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:onnxruntime/onnxruntime.dart';

import '../app_config.dart';
import 'arabic_normalizer.dart';

class IntentResult {
  final String label;
  final double confidence;
  final List<MapEntry<String, double>> top;
  const IntentResult(this.label, this.confidence, this.top);
  bool get confident => confidence >= AppConfig.confidenceThreshold;
}

/// Runs the CNN-BiLSTM (ONNX) fully on-device.
class IntentClassifier {
  IntentClassifier._(this._session, this._vocab, this._labels, this._maxLen);

  final OrtSession _session;
  final Map<String, int> _vocab;
  final List<String> _labels;
  final int _maxLen;

  /// Returns null (instead of crashing the app) if the model can't be loaded.
  static Future<IntentClassifier?> tryLoad() async {
    try {
      OrtEnv.instance.init();
      final vocabRaw = jsonDecode(await rootBundle.loadString('assets/model/vocab.json'))
          as Map<String, dynamic>;
      final vocab = vocabRaw.map((k, v) => MapEntry(k, (v as num).toInt()));
      final labels = (jsonDecode(await rootBundle.loadString('assets/model/labels.json'))
              as List)
          .cast<String>();
      final cfg = jsonDecode(await rootBundle.loadString('assets/model/config.json'))
          as Map<String, dynamic>;
      final bytes =
          (await rootBundle.load('assets/model/intent_model.onnx')).buffer.asUint8List();
      final session = OrtSession.fromBuffer(bytes, OrtSessionOptions());
      return IntentClassifier._(session, vocab, labels, (cfg['max_len'] as num).toInt());
    } catch (e, st) {
      debugPrint('IntentClassifier load failed: $e\n$st');
      return null;
    }
  }

  IntentResult classify(String text) {
    final ids = ArabicNormalizer.encode(text, _vocab, _maxLen);
    // Model input is int64 [1, maxLen].
    final input = OrtValueTensor.createTensorWithDataList(ids, [1, _maxLen]);
    final opts = OrtRunOptions();
    List<OrtValue?>? outputs;
    try {
      outputs = _session.run(opts, {'input_ids': input});
      final first = (outputs == null || outputs.isEmpty) ? null : outputs[0];
      if (first == null) throw StateError('ONNX returned no output');
      final logits = ((first.value as List).first as List)
          .map((e) => (e as num).toDouble())
          .toList();
      final mx = logits.reduce(math.max);
      final exps = logits.map((l) => math.exp(l - mx)).toList();
      final sum = exps.reduce((a, b) => a + b);
      final probs = exps.map((e) => e / sum).toList();
      final order = List<int>.generate(probs.length, (i) => i)
        ..sort((a, b) => probs[b].compareTo(probs[a]));
      return IntentResult(
        _labels[order.first],
        probs[order.first],
        order.take(3).map((i) => MapEntry(_labels[i], probs[i])).toList(),
      );
    } finally {
      input.release();
      opts.release();
      outputs?.forEach((o) => o?.release());
    }
  }

  void dispose() {
    _session.release();
  }
}
