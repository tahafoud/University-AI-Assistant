import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../app_config.dart';
import '../../core/format.dart';
import '../../data/models.dart';
import '../../logic/announcements_controller.dart';
import '../../theme/app_theme.dart';

class AnnouncementsScreen extends StatelessWidget {
  const AnnouncementsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final c = context.watch<AnnouncementsController>();
    final cs = Theme.of(context).colorScheme;

    return Column(
      children: [
        _StatusBanner(c: c),
        Expanded(
          child: RefreshIndicator(
            onRefresh: () => c.sync(force: true),
            child: !c.loaded
                ? const Center(child: CircularProgressIndicator())
                : c.items.isEmpty
                    ? ListView(children: [
                        SizedBox(height: MediaQuery.sizeOf(context).height * 0.2),
                        Icon(Icons.campaign_outlined, size: 64, color: cs.outline),
                        const SizedBox(height: 12),
                        Center(
                          child: Text('لا توجد إعلانات محفوظة بعد\nاسحب للأسفل للتحديث',
                              textAlign: TextAlign.center,
                              style: TextStyle(color: cs.outline, height: 1.6)),
                        ),
                      ])
                    : ListView.builder(
                        physics: const AlwaysScrollableScrollPhysics(),
                        padding: const EdgeInsets.fromLTRB(14, 6, 14, 16),
                        itemCount: c.items.length,
                        itemBuilder: (_, i) => _AnnouncementCard(a: c.items[i]),
                      ),
          ),
        ),
      ],
    );
  }
}

class _StatusBanner extends StatelessWidget {
  const _StatusBanner({required this.c});
  final AnnouncementsController c;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    String? text;
    IconData icon = Icons.cloud_done_outlined;
    Color color = cs.primary;
    if (c.syncing) {
      text = 'جارٍ تحديث الإعلانات...';
      icon = Icons.sync_rounded;
    } else if (c.offline) {
      text = c.lastSync == null
          ? 'لا يوجد اتصال — لم يتم التحديث بعد'
          : 'أنت غير متصل — آخر تحديث ${fmtAgo(c.lastSync!)}';
      icon = Icons.cloud_off_rounded;
      color = AppColors.gold;
    }
    return AnimatedSize(
      duration: const Duration(milliseconds: 250),
      child: text == null
          ? const SizedBox(width: double.infinity)
          : Container(
              width: double.infinity,
              margin: const EdgeInsets.fromLTRB(14, 4, 14, 6),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: withA(color, 0.12),
                borderRadius: BorderRadius.circular(14),
              ),
              child: Row(children: [
                Icon(icon, size: 18, color: color),
                const SizedBox(width: 8),
                Expanded(child: Text(text, style: TextStyle(fontSize: 13, color: cs.onSurface))),
              ]),
            ),
    );
  }
}

class _AnnouncementCard extends StatefulWidget {
  const _AnnouncementCard({required this.a});
  final Announcement a;
  @override
  State<_AnnouncementCard> createState() => _AnnouncementCardState();
}

class _AnnouncementCardState extends State<_AnnouncementCard> {
  bool _open = false;

  @override
  Widget build(BuildContext context) {
    final a = widget.a;
    final cs = Theme.of(context).colorScheme;
    final text = a.text.isEmpty ? 'إعلان مصوّر' : a.text;
    final long = text.length > 220 || '\n'.allMatches(text).length > 4;

    return Card(
      elevation: 0,
      margin: const EdgeInsets.symmetric(vertical: 6),
      color: cs.surfaceContainerHighest.withAlpha(110),
      shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: BorderSide(color: withA(cs.outline, 0.15))),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: long ? () => setState(() => _open = !_open) : null,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (a.hasImage)
              Image.network(
                AppConfig.mediaUrl(a.mediaName!),
                height: 190,
                fit: BoxFit.cover,
                loadingBuilder: (_, child, p) => p == null
                    ? child
                    : const SizedBox(
                        height: 190, child: Center(child: CircularProgressIndicator())),
                errorBuilder: (_, __, ___) => const SizedBox.shrink(), // offline
              ),
            Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                      decoration: BoxDecoration(
                          color: withA(AppColors.teal, 0.14),
                          borderRadius: BorderRadius.circular(20)),
                      child: Text(fmtDate(a.date),
                          style: const TextStyle(
                              fontSize: 12,
                              color: AppColors.teal,
                              fontWeight: FontWeight.w700)),
                    ),
                    const Spacer(),
                    if (long)
                      Icon(_open ? Icons.expand_less_rounded : Icons.expand_more_rounded,
                          color: cs.outline),
                  ]),
                  const SizedBox(height: 10),
                  AnimatedSize(
                    duration: const Duration(milliseconds: 250),
                    alignment: Alignment.topCenter,
                    child: Text(text,
                        maxLines: _open ? null : 5,
                        overflow: _open ? TextOverflow.visible : TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 15, height: 1.6)),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
