/// Dart port of arabic_text.clean_arabic_text(level="nlp") from the Python side.
/// MUST stay identical, otherwise the model sees different input than in
/// training. test/normalizer_parity_test.dart checks it against golden_tests.json.
///
/// Known deviation: Dart has no built-in NFKC. We only map the Arabic lam-alef
/// presentation ligatures by hand (keyboard input never contains them anyway).
class ArabicNormalizer {
  static final _invisible =
      RegExp(r'[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]');
  static final _tashkeel = RegExp(r'[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]');
  static final _emoji = RegExp(
      r'[\u{1F000}-\u{1FAFF}\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]',
      unicode: true);
  static final _url =
      RegExp(r'(https?://\S+|www\.\S+|t\.me/\S+)', caseSensitive: false);
  static final _alefs = RegExp('[إأآٱ]');
  static final _repeat = RegExp(r'(.)\1{2,}');
  static final _nonWord = RegExp(r'[^\u0621-\u063A\u0641-\u064Aa-zA-Z0-9\s]');
  static final _spaces = RegExp(r'\s+');

  static const _ligatures = {
    '\uFEFB': 'لا', '\uFEFC': 'لا',
    '\uFEF7': 'لا', '\uFEF8': 'لا',
    '\uFEF9': 'لا', '\uFEFA': 'لا',
    '\uFEF5': 'لا', '\uFEF6': 'لا',
  };

  /// Arabic-Indic (٠-٩) and Persian (۰-۹) digits -> 0-9
  static String digitsToWestern(String s) {
    final b = StringBuffer();
    for (final r in s.runes) {
      if (r >= 0x0660 && r <= 0x0669) {
        b.writeCharCode(0x30 + (r - 0x0660));
      } else if (r >= 0x06F0 && r <= 0x06F9) {
        b.writeCharCode(0x30 + (r - 0x06F0));
      } else {
        b.writeCharCode(r);
      }
    }
    return b.toString();
  }

  static String normalize(String text) {
    if (text.isEmpty) return '';
    var t = text.replaceAll(_invisible, '').replaceAll('\u0640', '');
    _ligatures.forEach((k, v) => t = t.replaceAll(k, v));
    t = t.replaceAll(_tashkeel, '');
    t = t.replaceAll(_emoji, ' ');
    t = digitsToWestern(t);
    t = t.replaceAll(_url, ' ');
    t = t
        .replaceAll(_alefs, 'ا')
        .replaceAll('ى', 'ي')
        .replaceAll('ة', 'ه')
        .replaceAll('ؤ', 'و')
        .replaceAll('ئ', 'ي');
    t = t.replaceAllMapped(_repeat, (m) => '${m[1]}${m[1]}');
    t = t.replaceAll(_nonWord, ' ');
    t = t.replaceAll(_spaces, ' ').trim();
    return t.toLowerCase();
  }

  /// chars -> vocabulary ids, truncated/padded to [maxLen] (0 = PAD, 1 = UNK).
  static List<int> encode(String text, Map<String, int> vocab, int maxLen) {
    final ids = <int>[];
    for (final r in normalize(text).runes) {
      ids.add(vocab[String.fromCharCode(r)] ?? 1);
      if (ids.length >= maxLen) break;
    }
    while (ids.length < maxLen) {
      ids.add(0);
    }
    return ids;
  }

  /// Crude Arabic stemming used only for announcement retrieval.
  static String stem(String token) {
    var s = token;
    if (s.startsWith('ال') && s.length > 4) s = s.substring(2);
    for (final suf in const ['ات', 'ون', 'ين', 'ها', 'ه']) {
      if (s.length > 4 && s.endsWith(suf)) {
        s = s.substring(0, s.length - suf.length);
        break;
      }
    }
    return s;
  }
}
