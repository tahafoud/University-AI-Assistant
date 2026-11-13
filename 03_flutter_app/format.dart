String two(int n) => n.toString().padLeft(2, '0');

String fmtDate(DateTime d) => '${d.year}/${two(d.month)}/${two(d.day)}';

String fmtTime(DateTime d) => '${two(d.hour)}:${two(d.minute)}';

String fmtAgo(DateTime d) {
  final diff = DateTime.now().difference(d);
  if (diff.inMinutes < 1) return 'الآن';
  if (diff.inMinutes < 60) return 'منذ ${diff.inMinutes} دقيقة';
  if (diff.inHours < 24) return 'منذ ${diff.inHours} ساعة';
  return 'منذ ${diff.inDays} يوم';
}
