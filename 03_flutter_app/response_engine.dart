import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show rootBundle;

import '../core/arabic_normalizer.dart';
import '../core/format.dart';
import '../core/intent_classifier.dart';
import '../data/announcement_repository.dart';
import '../data/models.dart';

class IntentKnowledge {
  final List<String> answers;
  final bool retrieve;
  final List<String> keywords;
  final String? noMatch;
  const IntentKnowledge(this.answers, this.retrieve, this.keywords, this.noMatch);
}

/// Static answers + suggestions, loaded from assets/knowledge.json.
/// Replace/extend this with the university's official FAQ (Excel -> JSON).
class KnowledgeBase {
  final List<String> suggestions;
  final Map<String, IntentKnowledge> intents;
  final String fallbackAnswer;
  final String relatedPrefix;
  const KnowledgeBase(
      this.suggestions, this.intents, this.fallbackAnswer, this.relatedPrefix);

  static Future<KnowledgeBase> load() async {
    final j = jsonDecode(await rootBundle.loadString('assets/knowledge.json'))
        as Map<String, dynamic>;
    final intents = <String, IntentKnowledge>{};
    (j['intents'] as Map<String, dynamic>).forEach((k, v) {
      final m = v as Map<String, dynamic>;
      intents[k] = IntentKnowledge(
        (m['answers'] as List).cast<String>(),
        (m['retrieve'] as bool?) ?? false,
        ((m['keywords'] as List?) ?? const [])
            .cast<String>()
            .map(ArabicNormalizer.normalize)
            .toList(),
        m['no_match'] as String?,
      );
    });
    final fb = j['fallback'] as Map<String, dynamic>;
    return KnowledgeBase((j['suggestions'] as List).cast<String>(), intents,
        fb['answer'] as String, fb['related_prefix'] as String);
  }
}

class BotReply {
  final String text;
  final String intent;
  final double? confidence;
  const BotReply(this.text, this.intent, this.confidence);
}

class ResponseEngine {
  ResponseEngine(this.kb, this._announcements);
  final KnowledgeBase kb;
  final AnnouncementRepository _announcements;
  final _rng = Random();

  Future<BotReply> reply({
    required String userText,
    required Student student,
    required IntentClassifier? classifier,
  }) async {
    IntentResult? r;
    if (classifier != null) {
      try {
        r = classifier.classify(userText);
      } catch (e) {
        debugPrint('classify failed: $e');
      }
    }

    final k = (r != null && r.confident) ? kb.intents[r.label] : null;
    if (r == null || k == null) {
      // Low confidence / no model: keyword retrieval over saved announcements.
      final related = await _announcements.search(userText, limit: 2);
      final b = StringBuffer(kb.fallbackAnswer);
      if (related.isNotEmpty) {
        b.write('\n\n${kb.relatedPrefix}\n${related.map(_fmt).join('\n')}');
      }
      return BotReply(b.toString(), 'unknown', r?.confidence);
    }

    final first = student.name.trim().split(' ').first;
    final answer =
        k.answers[_rng.nextInt(k.answers.length)].replaceAll('{name}', first);

    if (r.label == 'latest_announcements') {
      final latest = await _announcements.latest(limit: 3);
      final text = latest.isEmpty
          ? (k.noMatch ?? answer)
          : '$answer\n\n${latest.map(_fmt).join('\n')}';
      return BotReply(text, r.label, r.confidence);
    }

    if (!k.retrieve) return BotReply(answer, r.label, r.confidence);

    final related = await _announcements.search(userText,
        extraKeywords: k.keywords, limit: 3);
    final text = related.isEmpty
        ? '$answer\n\n${k.noMatch ?? ''}'.trim()
        : '$answer\n\n📌 أحدث الإعلانات ذات الصلة:\n${related.map(_fmt).join('\n')}';
    return BotReply(text, r.label, r.confidence);
  }

  String _fmt(Announcement a) {
    var t = a.text.replaceAll(RegExp(r'\s+'), ' ').trim();
    if (t.isEmpty) t = 'إعلان مصوّر';
    if (t.length > 160) t = '${t.substring(0, 160)}…';
    return '• ${fmtDate(a.date)} — $t';
  }
}
