import 'package:flutter/foundation.dart';

import '../core/intent_classifier.dart';
import '../data/chat_repository.dart';
import '../data/models.dart';
import 'response_engine.dart';

class ChatController extends ChangeNotifier {
  ChatController({
    required this.student,
    required ChatRepository repo,
    required ResponseEngine engine,
    required IntentClassifier? classifier,
  })  : _repo = repo,
        _engine = engine,
        _classifier = classifier;

  final Student student;
  final ChatRepository _repo;
  final ResponseEngine _engine;
  final IntentClassifier? _classifier;

  List<String> get suggestions => _engine.kb.suggestions;

  List<Conversation> conversations = [];
  int? activeId;
  List<ChatMessage> messages = [];
  bool typing = false;
  bool ready = false;
  bool _disposed = false;

  Future<void> init() async {
    conversations = await _repo.conversations(student.id);
    if (conversations.isNotEmpty) {
      activeId = conversations.first.id;
      messages = await _repo.messages(activeId!, student.id);
    }
    ready = true;
    _notify();
  }

  Future<void> open(int id) async {
    activeId = id;
    messages = await _repo.messages(id, student.id);
    _notify();
  }

  void newChat() {
    activeId = null;
    messages = [];
    _notify();
  }

  Future<void> delete(int id) async {
    await _repo.deleteConversation(id, student.id);
    conversations = await _repo.conversations(student.id);
    if (activeId == id) {
      activeId = null;
      messages = [];
    }
    _notify();
  }

  Future<void> send(String text) async {
    if (typing || text.trim().isEmpty) return;
    var convId = activeId;
    if (convId == null) {
      final c = await _repo.createConversation(student.id, title: _titleFrom(text));
      convId = c.id;
      activeId = c.id;
      conversations = [c, ...conversations];
    }
    final userMsg = await _repo.addMessage(
        conversationId: convId, studentId: student.id, isUser: true, text: text.trim());
    messages = [...messages, userMsg];
    typing = true;
    _notify();

    try {
      final started = DateTime.now();
      final reply = await _engine.reply(
          userText: text, student: student, classifier: _classifier);
      const minTyping = Duration(milliseconds: 600); // natural feel
      final elapsed = DateTime.now().difference(started);
      if (elapsed < minTyping) await Future.delayed(minTyping - elapsed);

      final bot = await _repo.addMessage(
        conversationId: convId,
        studentId: student.id,
        isUser: false,
        text: reply.text,
        intent: reply.intent,
        confidence: reply.confidence,
      );
      if (activeId == convId) messages = [...messages, bot];
    } catch (e, st) {
      debugPrint('send failed: $e\n$st');
      final err = await _repo.addMessage(
        conversationId: convId,
        studentId: student.id,
        isUser: false,
        text: 'حدث خطأ غير متوقع، حاول مرة أخرى.',
      );
      if (activeId == convId) messages = [...messages, err];
    } finally {
      typing = false;
      conversations = await _repo.conversations(student.id);
      _notify();
    }
  }

  String _titleFrom(String text) {
    final t = text.replaceAll('\n', ' ').trim();
    return t.length > 32 ? '${t.substring(0, 32)}…' : t;
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}
