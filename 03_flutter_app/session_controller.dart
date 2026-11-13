import 'package:flutter/foundation.dart';

import '../data/auth_repository.dart';
import '../data/models.dart';

class SessionController extends ChangeNotifier {
  SessionController(this._auth);
  final AuthRepository _auth;

  Student? student;
  bool initialized = false;
  bool busy = false;
  String? error;

  Future<void> init() async {
    student = await _auth.restoreSession();
    initialized = true;
    notifyListeners();
  }

  Future<void> submit({
    required bool register,
    required String studentId,
    required String name,
    required String pin,
  }) async {
    busy = true;
    error = null;
    notifyListeners();
    try {
      student = register
          ? await _auth.register(studentId: studentId, name: name, pin: pin)
          : await _auth.login(studentId: studentId, pin: pin);
    } on AuthException catch (e) {
      error = e.message;
    } catch (e) {
      debugPrint('auth error: $e');
      error = 'حدث خطأ غير متوقع';
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  void clearError() {
    if (error != null) {
      error = null;
      notifyListeners();
    }
  }

  Future<void> logout() async {
    await _auth.logout();
    student = null;
    error = null;
    notifyListeners();
  }
}
