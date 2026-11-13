import 'package:sqflite/sqflite.dart';

import 'core/intent_classifier.dart';
import 'data/announcement_repository.dart';
import 'data/app_database.dart';
import 'data/auth_repository.dart';
import 'data/chat_repository.dart';
import 'logic/response_engine.dart';

/// Manual dependency container (kept simple on purpose).
class AppDeps {
  AppDeps._(this.db, this.auth, this.chat, this.announcements, this.kb,
      this.classifier)
      : engine = ResponseEngine(kb, announcements);

  final Database db;
  final AuthRepository auth;
  final ChatRepository chat;
  final AnnouncementRepository announcements;
  final KnowledgeBase kb;
  final IntentClassifier? classifier; // null => retrieval-only mode
  final ResponseEngine engine;

  static Future<AppDeps> create() async {
    final db = await AppDatabase.open();
    final kb = await KnowledgeBase.load();
    final classifier = await IntentClassifier.tryLoad();
    return AppDeps._(db, AuthRepository(db), ChatRepository(db),
        AnnouncementRepository(db), kb, classifier);
  }
}
