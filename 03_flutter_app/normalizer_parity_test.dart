import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:university_ai_chat/core/arabic_normalizer.dart';

void main() {
  test('normalizer basics', () {
    expect(ArabicNormalizer.normalize('أُعلِنَتْ نتـــائجُ الامتحاناتِ'),
        'اعلنت نتايج الامتحانات');
    expect(ArabicNormalizer.normalize('٢٠٢٦/١١/٠٥ 🎉🎉 https://t.me/x'), '2026 11 05');
    expect(ArabicNormalizer.digitsToWestern('٠١٢٣٤٥٦٧٨٩'), '0123456789');
  });

  // Proves Dart == Python: needs assets/model/{golden_tests,vocab,config}.json
  test('golden parity with Python (normalized text + char ids)', () {
    final g = File('assets/model/golden_tests.json');
    final v = File('assets/model/vocab.json');
    final c = File('assets/model/config.json');
    if (!g.existsSync() || !v.existsSync() || !c.existsSync()) {
      markTestSkipped('copy model artifacts into assets/model/ first');
      return;
    }
    final vocab = (jsonDecode(v.readAsStringSync()) as Map<String, dynamic>)
        .map((k, x) => MapEntry(k, (x as num).toInt()));
    final maxLen = (jsonDecode(c.readAsStringSync())['max_len'] as num).toInt();
    for (final t in jsonDecode(g.readAsStringSync()) as List) {
      final input = t['input'] as String;
      expect(ArabicNormalizer.normalize(input), t['normalized'], reason: input);
      expect(ArabicNormalizer.encode(input, vocab, maxLen),
          (t['ids'] as List).cast<int>(),
          reason: input);
    }
  });
}
