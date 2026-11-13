import 'dart:async';
import 'dart:convert';
import 'dart:io' show SocketException;
import 'dart:math' show min;

import 'package:http/http.dart' as http;
import 'package:sqflite/sqflite.dart';

import '../app_config.dart';
import '../core/arabic_normalizer.dart';
import 'models.dart';

class SyncResult {
  final bool ok;
  final bool skipped;
  final bool notModified;
  final int added, updated, removed;
  final String? error;
  const SyncResult({
    this.ok = true,
    this.skipped = false,
    this.notModified = false,
    this.added = 0,
    this.updated = 0,
    this.removed = 0,
    this.error,
  });
}

/// Offline-first: the UI ALWAYS reads from SQLite. sync() just refreshes the
/// local copy when a network is available (conditional GET, upsert by hash,
/// removal of announcements deleted upstream).
class AnnouncementRepository {
  AnnouncementRepository(this._db, {http.Client? client})
      : _client = client ?? http.Client();
  final Database _db;
  final http.Client _client;
  bool _syncing = false;

  static const _stop = {
    'متي', 'كيف', 'ماذا', 'ما', 'هي', 'هل', 'اين', 'وين', 'ابغي', 'اريد',
    'عن', 'علي', 'الي', 'في', 'من', 'لو', 'سمحت', 'ممكن', 'كم', 'ايش', 'وش',
  };

  Future<String?> _meta(String key) async {
    final r = await _db.query('meta', where: 'key = ?', whereArgs: [key], limit: 1);
    return r.isEmpty ? null : r.first['value'] as String?;
  }

  Future<void> _setMeta(DatabaseExecutor ex, String key, String value) async {
    await ex.insert('meta', {'key': key, 'value': value},
        conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<DateTime?> lastSync() async {
    final v = await _meta('last_sync');
    final ms = v == null ? null : int.tryParse(v);
    return ms == null ? null : DateTime.fromMillisecondsSinceEpoch(ms);
  }

  Future<SyncResult> sync({bool force = false}) async {
    if (_syncing) return const SyncResult(skipped: true);
    _syncing = true;
    try {
      if (!force) {
        final last = await lastSync();
        if (last != null &&
            DateTime.now().difference(last) < AppConfig.minSyncInterval) {
          return const SyncResult(skipped: true);
        }
      }
      final headers = <String, String>{'Accept': 'application/json'};
      if (!force) {
        final etag = await _meta('etag');
        final lm = await _meta('last_modified');
        if (etag != null) headers['If-None-Match'] = etag;
        if (lm != null) headers['If-Modified-Since'] = lm;
      }
      final res = await _client
          .get(Uri.parse('${AppConfig.baseUrl}${AppConfig.announcementsPath}'),
              headers: headers)
          .timeout(AppConfig.syncTimeout);

      final nowMs = DateTime.now().millisecondsSinceEpoch.toString();
      if (res.statusCode == 304) {
        await _setMeta(_db, 'last_sync', nowMs);
        return const SyncResult(notModified: true);
      }
      if (res.statusCode != 200) {
        return SyncResult(ok: false, error: 'HTTP ${res.statusCode}');
      }
      final body = jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
      final items = (body['items'] as List?) ?? const [];
      final r = await _apply(items);
      await _setMeta(_db, 'last_sync', nowMs);
      final etag = res.headers['etag'];
      final lm = res.headers['last-modified'];
      if (etag != null) await _setMeta(_db, 'etag', etag);
      if (lm != null) await _setMeta(_db, 'last_modified', lm);
      return r;
    } on TimeoutException {
      return const SyncResult(ok: false, error: 'timeout');
    } on SocketException {
      return const SyncResult(ok: false, error: 'offline');
    } on http.ClientException {
      return const SyncResult(ok: false, error: 'offline');
    } on FormatException {
      return const SyncResult(ok: false, error: 'bad_data');
    } catch (e) {
      return SyncResult(ok: false, error: e.toString());
    } finally {
      _syncing = false;
    }
  }

  Future<SyncResult> _apply(List items) async {
    final existing = <int, String?>{};
    for (final r in await _db.query('announcements', columns: ['id', 'content_hash'])) {
      existing[r['id'] as int] = r['content_hash'] as String?;
    }
    var added = 0, updated = 0, removed = 0;
    final feedIds = <int>{};

    await _db.transaction((txn) async {
      final batch = txn.batch();
      for (final raw in items) {
        final m = raw as Map<String, dynamic>;
        final id = (m['id'] as num).toInt();
        feedIds.add(id);
        final hash = (m['hash'] ?? '') as String;
        final known = existing.containsKey(id);
        if (known && hash.isNotEmpty && existing[id] == hash) continue;

        final text = ((m['text'] ?? '') as String).trim();
        final media = m['media'] as String?;
        batch.insert(
          'announcements',
          {
            'id': id,
            'date_utc': m['date'] as String,
            'text': text,
            'text_search': ArabicNormalizer.normalize(text),
            'media_type': m['media_type'],
            'media_name': media?.split(RegExp(r'[\\/]')).last,
            'content_hash': hash,
          },
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
        if (known) {
          updated++;
        } else {
          added++;
        }
      }
      // Remove items deleted upstream, but only inside the feed's window.
      if (feedIds.isNotEmpty) {
        final minId = feedIds.reduce(min);
        for (final id in existing.keys) {
          if (id >= minId && !feedIds.contains(id)) {
            batch.delete('announcements', where: 'id = ?', whereArgs: [id]);
            removed++;
          }
        }
      }
      await batch.commit(noResult: true);
    });
    return SyncResult(added: added, updated: updated, removed: removed);
  }

  Future<List<Announcement>> latest({int limit = 100}) async {
    final rows = await _db.query('announcements',
        orderBy: 'date_utc DESC, id DESC', limit: limit);
    return rows.map(Announcement.fromMap).toList();
  }

  /// Simple keyword retrieval over the 300 most recent announcements.
  Future<List<Announcement>> search(String query,
      {List<String> extraKeywords = const [], int limit = 3}) async {
    final tokens = <String>{};
    for (final t in ArabicNormalizer.normalize(query).split(' ')) {
      if (t.length >= 3 && !_stop.contains(t)) tokens.add(ArabicNormalizer.stem(t));
    }
    for (final k in extraKeywords) {
      tokens.add(ArabicNormalizer.stem(k));
    }
    tokens.removeWhere((t) => t.length < 3);
    if (tokens.isEmpty) return [];

    final rows = await _db.query('announcements',
        orderBy: 'date_utc DESC, id DESC', limit: 300);
    final scored = <MapEntry<int, Map<String, Object?>>>[];
    for (final r in rows) {
      final hay = r['text_search'] as String;
      final score = tokens.where(hay.contains).length;
      if (score > 0) scored.add(MapEntry(score, r));
    }
    // stable sort: higher score first, recency preserved among equals
    final indexed = scored.asMap().entries.toList()
      ..sort((a, b) {
        final c = b.value.key.compareTo(a.value.key);
        return c != 0 ? c : a.key.compareTo(b.key);
      });
    return indexed
        .take(limit)
        .map((e) => Announcement.fromMap(e.value.value))
        .toList();
  }
}
