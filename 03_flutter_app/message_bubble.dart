import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../../core/format.dart';
import '../../data/models.dart';
import '../../theme/app_theme.dart';

class BotAvatar extends StatelessWidget {
  const BotAvatar({super.key});
  @override
  Widget build(BuildContext context) => CircleAvatar(
        radius: 16,
        backgroundColor: withA(AppColors.teal, 0.15),
        child: const Icon(Icons.auto_awesome_rounded, size: 18, color: AppColors.teal),
      );
}

class MessageBubble extends StatelessWidget {
  const MessageBubble({super.key, required this.message});
  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final isUser = message.isUser;
    final fresh = DateTime.now().difference(message.createdAt) < const Duration(seconds: 2);

    final bubble = Container(
      constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.78),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        gradient: isUser ? AppTheme.gradient : null,
        color: isUser ? null : cs.surfaceContainerHighest,
        borderRadius: BorderRadiusDirectional.only(
          topStart: const Radius.circular(18),
          topEnd: const Radius.circular(18),
          bottomStart: Radius.circular(isUser ? 4 : 18),
          bottomEnd: Radius.circular(isUser ? 18 : 4),
        ),
        boxShadow: [
          BoxShadow(
              color: withA(Colors.black, 0.06),
              blurRadius: 8,
              offset: const Offset(0, 3)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SelectableText(
            message.text,
            style: TextStyle(
                color: isUser ? Colors.white : cs.onSurface, fontSize: 15.5, height: 1.6),
          ),
          const SizedBox(height: 4),
          Text(
            fmtTime(message.createdAt) +
                (kDebugMode && !isUser && message.intent != null
                    ? '  ·  ${message.intent} ${((message.confidence ?? 0) * 100).round()}%'
                    : ''),
            style: TextStyle(
                fontSize: 11, color: isUser ? withA(Colors.white, 0.75) : cs.outline),
          ),
        ],
      ),
    );

    final row = Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(
        // start = right edge in RTL (user), end = left edge (bot)
        mainAxisAlignment: isUser ? MainAxisAlignment.start : MainAxisAlignment.end,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: isUser
            ? [Flexible(child: bubble)]
            : [Flexible(child: bubble), const SizedBox(width: 8), const BotAvatar()],
      ),
    );

    if (!fresh) return row;
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: const Duration(milliseconds: 320),
      curve: Curves.easeOutCubic,
      builder: (_, v, child) => Opacity(
        opacity: v,
        child: Transform.translate(offset: Offset(0, 14 * (1 - v)), child: child),
      ),
      child: row,
    );
  }
}
