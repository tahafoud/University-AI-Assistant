import 'package:flutter/foundation.dart';

import '../data/announcement_repository.dart';
import '../data/models.dart';

class AnnouncementsController extends ChangeNotifier {
  AnnouncementsController(this._repo) {
    _reload();
  }
  final AnnouncementRepository _repo;

  List<Announcement> items = [];
  bool loaded = false;
  bool syncing = false;
  bool offline = false;
  DateTime? lastSync;
  bool _disposed = false;

  Future<void> _reload() async {
    items = await _repo.latest(limit: 100);
    lastSync = await _repo.lastSync();
    loaded = true;
    _notify();
  }

  /// Local data is shown immediately; sync only refreshes it.
  Future<void> sync({bool force = false}) async {
    if (syncing) return;
    syncing = true;
    _notify();
    final r = await _repo.sync(force: force);
    if (!r.skipped) offline = !r.ok;
    if (!r.skipped && r.ok) await _reload();
    syncing = false;
    _notify();
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
