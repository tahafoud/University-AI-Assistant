import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../app_deps.dart';
import '../../logic/chat_controller.dart';
import '../../logic/session_controller.dart';
import '../../theme/app_theme.dart';
import '../widgets/app_logo.dart';
import 'home_shell.dart';
import 'login_screen.dart';

/// Decides between splash / login / home based on the persisted session.
class SplashGate extends StatelessWidget {
  const SplashGate({super.key});

  @override
  Widget build(BuildContext context) {
    final session = context.watch<SessionController>();
    final deps = context.read<AppDeps>();
    final student = session.student;

    final Widget child;
    if (!session.initialized) {
      child = const _Splash(key: ValueKey('splash'));
    } else if (student == null) {
      child = const LoginScreen(key: ValueKey('login'));
    } else {
      child = ChangeNotifierProvider<ChatController>(
        key: ValueKey('home_${student.id}'),
        create: (_) => ChatController(
          student: student,
          repo: deps.chat,
          engine: deps.engine,
          classifier: deps.classifier,
        )..init(),
        child: const HomeShell(),
      );
    }
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 450),
      switchInCurve: Curves.easeOut,
      child: child,
    );
  }
}

class _Splash extends StatelessWidget {
  const _Splash({super.key});
  @override
  Widget build(BuildContext context) => Scaffold(
        body: Container(
          decoration: const BoxDecoration(gradient: AppTheme.gradient),
          child: const Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                AppLogo(size: 96),
                SizedBox(height: 28),
                SizedBox(
                  width: 26,
                  height: 26,
                  child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white),
                ),
              ],
            ),
          ),
        ),
      );
}
