import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

/// Local SQLite. Every student-owned table is filtered by student_id, so
/// chat histories never mix between accounts on the same phone.
class AppDatabase {
  static const _version = 1;

  static Future<Database> open() async {
    final path = p.join(await getDatabasesPath(), 'university_chat.db');
    return openDatabase(
      path,
      version: _version,
      onConfigure: (db) => db.execute('PRAGMA foreign_keys = ON'),
      onCreate: (db, v) async {
        await db.execute('''
          CREATE TABLE students (
            student_id TEXT PRIMARY KEY,
            name       TEXT NOT NULL,
            pin_salt   TEXT NOT NULL,
            pin_hash   TEXT NOT NULL,
            created_at INTEGER NOT NULL
          )''');
        await db.execute('''
          CREATE TABLE conversations (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
            title      TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
          )''');
        await db.execute('''
          CREATE TABLE messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            student_id      TEXT NOT NULL,
            role            TEXT NOT NULL CHECK (role IN ('user','bot')),
            text            TEXT NOT NULL,
            intent          TEXT,
            confidence      REAL,
            created_at      INTEGER NOT NULL
          )''');
        await db.execute('''
          CREATE TABLE announcements (
            id           INTEGER PRIMARY KEY,
            date_utc     TEXT NOT NULL,
            text         TEXT NOT NULL,
            text_search  TEXT NOT NULL,
            media_type   TEXT,
            media_name   TEXT,
            content_hash TEXT
          )''');
        await db.execute('CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)');
        await db.execute(
            'CREATE INDEX idx_conv_student ON conversations(student_id, updated_at DESC)');
        await db.execute(
            'CREATE INDEX idx_msg_conv ON messages(conversation_id, created_at)');
        await db.execute(
            'CREATE INDEX idx_ann_date ON announcements(date_utc DESC)');
      },
      // Future schema changes: bump _version and add migrations here.
      onUpgrade: (db, oldV, newV) async {},
    );
  }
}
