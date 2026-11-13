import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sqflite/sqflite.dart';

import '../core/arabic_normalizer.dart';
import 'models.dart';

class AuthException implements Exception {
  final String message;
  AuthException(this.message);
  @override
  String toString() => message;
}

/// LOCAL accounts: the student number + a PIN stored salted-and-hashed on the
/// device. This separates histories per student and locks casual access, but it
/// is NOT university authentication. For real SSO, implement the same three
/// methods against the university's API.
class AuthRepository {
  AuthRepository(this._db);
  final Database _db;
  static const _kSession = 'session_student_id';

  Future<Student?> restoreSession() async {
    final prefs = await SharedPreferences.getInstance();
    final id = prefs.getString(_kSession);
    if (id == null) return null;
    final rows = await _db.query('students',
        where: 'student_id = ?', whereArgs: [id], limit: 1);
    if (rows.isEmpty) {
      await prefs.remove(_kSession);
      return null;
    }
    return Student.fromMap(rows.first);
  }

  Future<Student> register(
      {required String studentId, required String name, required String pin}) async {
    final id = _validId(studentId);
    final p = _validPin(pin);
    final n = name.trim();
    if (n.length < 2) throw AuthException('الرجاء إدخال اسمك');
    final exists = await _db.query('students',
        where: 'student_id = ?', whereArgs: [id], limit: 1);
    if (exists.isNotEmpty) {
      throw AuthException('هذا الرقم الجامعي مسجّل مسبقاً، سجّل الدخول بدلاً من ذلك');
    }
    final salt = _newSalt();
    final now = DateTime.now().millisecondsSinceEpoch;
    await _db.insert('students', {
      'student_id': id,
      'name': n,
      'pin_salt': salt,
      'pin_hash': _hash(salt, p),
      'created_at': now,
    });
    await _saveSession(id);
    return Student(
        id: id, name: n, createdAt: DateTime.fromMillisecondsSinceEpoch(now));
  }

  Future<Student> login({required String studentId, required String pin}) async {
    final id = _validId(studentId);
    final p = _validPin(pin);
    final rows = await _db.query('students',
        where: 'student_id = ?', whereArgs: [id], limit: 1);
    if (rows.isEmpty) {
      throw AuthException('لا يوجد حساب بهذا الرقم، أنشئ حساباً جديداً أولاً');
    }
    final row = rows.first;
    if (_hash(row['pin_salt'] as String, p) != row['pin_hash']) {
      throw AuthException('الرمز السري غير صحيح');
    }
    await _saveSession(id);
    return Student.fromMap(row);
  }

  Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kSession);
  }

  Future<void> _saveSession(String id) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kSession, id);
  }

  String _validId(String raw) {
    final v = ArabicNormalizer.digitsToWestern(raw.trim());
    if (!RegExp(r'^\d{5,12}$').hasMatch(v)) {
      throw AuthException('أدخل رقماً جامعياً صحيحاً (5 إلى 12 رقماً)');
    }
    return v;
  }

  String _validPin(String raw) {
    final v = ArabicNormalizer.digitsToWestern(raw.trim());
    if (!RegExp(r'^\d{4,6}$').hasMatch(v)) {
      throw AuthException('الرمز السري يجب أن يكون من 4 إلى 6 أرقام');
    }
    return v;
  }

  String _newSalt() {
    final r = Random.secure();
    return base64Url.encode(List<int>.generate(16, (_) => r.nextInt(256)));
  }

  String _hash(String salt, String pin) {
    List<int> bytes = utf8.encode('$salt:$pin');
    for (var i = 0; i < 5000; i++) {
      bytes = sha256.convert(bytes).bytes;
    }
    return base64Encode(bytes);
  }
}
