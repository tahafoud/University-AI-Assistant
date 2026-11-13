import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../logic/chat_controller.dart';
import '../../theme/app_theme.dart';
import '../widgets/app_logo.dart';
import '../widgets/message_bubble.dart';
import '../widgets/typing_indicator.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});
  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _text = TextEditingController();

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  void _send([String? preset]) {
    final value = (preset ?? _text.text).trim();
    if (value.isEmpty) return;
    final chat = context.read<ChatController>();
    if (chat.typing) return;
    _text.clear();
    chat.send(value);
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<ChatController>(
      builder: (context, chat, _) {
        if (!chat.ready) {
          return const Center(child: CircularProgressIndicator());
        }
        final empty = chat.messages.isEmpty && !chat.typing;
        return Column(
          children: [
            Expanded(
              child: AnimatedSwitcher(
                duration: const Duration(milliseconds: 300),
                child: empty
                    ? _EmptyState(
                        key: const ValueKey('empty'),
                        name: chat.student.name,
                        suggestions: chat.suggestions,
                        onPick: _send,
                      )
                    : _MessageList(key: ValueKey('list_${chat.activeId}'), chat: chat),
              ),
            ),
            _InputBar(controller: _text, typing: chat.typing, onSend: _send),
          ],
        );
      },
    );
  }
}

class _MessageList extends StatelessWidget {
  const _MessageList({super.key, required this.chat});
  final ChatController chat;

  @override
  Widget build(BuildContext context) {
    final count = chat.messages.length + (chat.typing ? 1 : 0);
    return ListView.builder(
      reverse: true, // newest at the bottom, keeps position when keyboard opens
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 8),
      itemCount: count,
      itemBuilder: (_, index) {
        var i = index;
        if (chat.typing) {
          if (i == 0) return const TypingIndicator();
          i -= 1;
        }
        final m = chat.messages[chat.messages.length - 1 - i];
        return MessageBubble(key: ValueKey(m.id), message: m);
      },
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState(
      {super.key, required this.name, required this.suggestions, required this.onPick});
  final String name;
  final List<String> suggestions;
  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final first = name.trim().split(' ').first;
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.all(2),
              decoration: const BoxDecoration(shape: BoxShape.circle, gradient: AppTheme.gradient),
              child: const AppLogo(size: 76),
            ),
            const SizedBox(height: 18),
            Text('أهلاً $first 👋',
                style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w800)),
            const SizedBox(height: 6),
            Text('كيف أقدر أساعدك اليوم؟', style: TextStyle(color: cs.outline, fontSize: 15)),
            const SizedBox(height: 22),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              alignment: WrapAlignment.center,
              children: [
                for (final s in suggestions)
                  ActionChip(
                    label: Text(s),
                    avatar: const Icon(Icons.bolt_rounded, size: 18, color: AppColors.gold),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(20),
                        side: BorderSide(color: withA(cs.outline, 0.3))),
                    onPressed: () => onPick(s),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _InputBar extends StatelessWidget {
  const _InputBar({required this.controller, required this.typing, required this.onSend});
  final TextEditingController controller;
  final bool typing;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 6, 12, 10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: TextField(
                controller: controller,
                minLines: 1,
                maxLines: 5,
                textInputAction: TextInputAction.newline,
                decoration: InputDecoration(
                  hintText: 'اكتب سؤالك هنا...',
                  border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(26), borderSide: BorderSide.none),
                  enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(26),
                      borderSide: BorderSide(color: withA(cs.outline, 0.25))),
                  focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(26),
                      borderSide: BorderSide(color: cs.primary, width: 1.6)),
                ),
              ),
            ),
            const SizedBox(width: 8),
            ValueListenableBuilder<TextEditingValue>(
              valueListenable: controller,
              builder: (_, v, __) {
                final enabled = v.text.trim().isNotEmpty && !typing;
                return AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  width: 50,
                  height: 50,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: enabled ? AppTheme.gradient : null,
                    color: enabled ? null : withA(cs.outline, 0.25),
                  ),
                  child: IconButton(
                    onPressed: enabled ? onSend : null,
                    icon: Icon(Icons.send_rounded,
                        color: enabled ? Colors.white : cs.outline),
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}
