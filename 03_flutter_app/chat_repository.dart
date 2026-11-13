import 'package:sqflite/sqflite.dart';

import 'models.dart';

class ChatRepository {
  ChatRepository(this._db);
  final Database _db;

  Future<List<Conversation>> conversations(String studentId) async {
    final rows = await _db.query('conversations',
        where: 'student_id = ?',
        whereArgs: [studentId],
        orderBy: 'updated_at DESC, id DESC');
    return rows.map(Conversation.fromMap).toList();
  }

  Future<Conversation> createConversation(String studentId,
      {String title = 'محادثة جديدة'}) async {
    final now = DateTime.now().millisecondsSinceEpoch;
    final id = await _db.insert('conversations', {
      'student_id': studentId,
      'title': title,
      'created_at': now,
      'updated_at': now,
    });
    return Conversation(
        id: id,
        studentId: studentId,
        title: title,
        updatedAt: DateTime.fromMillisecondsSinceEpoch(now));
  }

  Future<List<ChatMessage>> messages(int conversationId, String studentId) async {
    final rows = await _db.query('messages',
        where: 'conversation_id = ? AND student_id = ?',
        whereArgs: [conversationId, studentId],
        orderBy: 'created_at ASC, id ASC');
    return rows.map(ChatMessage.fromMap).toList();
  }

  Future<ChatMessage> addMessage({
    required int conversationId,
    required String studentId,
    required bool isUser,
    required String text,
    String? intent,
    double? confidence,
  }) async {
    final now = DateTime.now().millisecondsSinceEpoch;
    late int id;
    await _db.transaction((txn) async {
      id = await txn.insert('messages', {
        'conversation_id': conversationId,
        'student_id': studentId,
        'role': isUser ? 'user' : 'bot',
        'text': text,
        'intent': intent,
        'confidence': confidence,
        'created_at': now,
      });
      await txn.update('conversations', {'updated_at': now},
          where: 'id = ? AND student_id = ?', whereArgs: [conversationId, studentId]);
    });
    return ChatMessage(
      id: id,
      conversationId: conversationId,
      isUser: isUser,
      text: text,
      intent: intent,
      confidence: confidence,
      createdAt: DateTime.fromMillisecondsSinceEpoch(now),
    );
  }

  Future<void> deleteConversation(int id, String studentId) async {
    // messages are removed by ON DELETE CASCADE
    await _db.delete('conversations',
        where: 'id = ? AND student_id = ?', whereArgs: [id, studentId]);
  }
}
