class Student {
  final String id;
  final String name;
  final DateTime createdAt;
  const Student({required this.id, required this.name, required this.createdAt});

  factory Student.fromMap(Map<String, Object?> m) => Student(
        id: m['student_id'] as String,
        name: m['name'] as String,
        createdAt: DateTime.fromMillisecondsSinceEpoch(m['created_at'] as int),
      );
}

class Conversation {
  final int id;
  final String studentId;
  final String title;
  final DateTime updatedAt;
  const Conversation(
      {required this.id,
      required this.studentId,
      required this.title,
      required this.updatedAt});

  factory Conversation.fromMap(Map<String, Object?> m) => Conversation(
        id: m['id'] as int,
        studentId: m['student_id'] as String,
        title: m['title'] as String,
        updatedAt: DateTime.fromMillisecondsSinceEpoch(m['updated_at'] as int),
      );
}

class ChatMessage {
  final int id;
  final int conversationId;
  final bool isUser;
  final String text;
  final String? intent;
  final double? confidence;
  final DateTime createdAt;
  const ChatMessage({
    required this.id,
    required this.conversationId,
    required this.isUser,
    required this.text,
    required this.createdAt,
    this.intent,
    this.confidence,
  });

  factory ChatMessage.fromMap(Map<String, Object?> m) => ChatMessage(
        id: m['id'] as int,
        conversationId: m['conversation_id'] as int,
        isUser: m['role'] == 'user',
        text: m['text'] as String,
        intent: m['intent'] as String?,
        confidence: (m['confidence'] as num?)?.toDouble(),
        createdAt: DateTime.fromMillisecondsSinceEpoch(m['created_at'] as int),
      );
}

class Announcement {
  final int id;
  final DateTime date;
  final String text;
  final String? mediaType;
  final String? mediaName;
  const Announcement(
      {required this.id,
      required this.date,
      required this.text,
      this.mediaType,
      this.mediaName});

  bool get hasImage =>
      mediaName != null && (mediaType == 'photo' || mediaType == 'image');

  factory Announcement.fromMap(Map<String, Object?> m) => Announcement(
        id: m['id'] as int,
        date: DateTime.parse(m['date_utc'] as String).toLocal(),
        text: m['text'] as String,
        mediaType: m['media_type'] as String?,
        mediaName: m['media_name'] as String?,
      );
}
