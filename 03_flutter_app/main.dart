import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:provider/provider.dart';

import 'app_deps.dart';
import 'logic/announcements_controller.dart';
import 'logic/session_controller.dart';
import 'theme/app_theme.dart';
import 'ui/screens/splash_gate.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final deps = await AppDeps.create();
  runApp(UniversityApp(deps: deps));
}

class UniversityApp extends StatelessWidget {
  const UniversityApp({super.key, required this.deps});
  final AppDeps deps;

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        Provider<AppDeps>.value(value: deps),
        ChangeNotifierProvider(create: (_) => SessionController(deps.auth)..init()),
        ChangeNotifierProvider(create: (_) => AnnouncementsController(deps.announcements)),
      ],
      child: MaterialApp(
        title: 'المساعد الجامعي',
        debugShowCheckedModeBanner: false,
        locale: const Locale('ar'),
        supportedLocales: const [Locale('ar')],
        localizationsDelegates: const [
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        theme: AppTheme.light(),
        darkTheme: AppTheme.dark(),
        themeMode: ThemeMode.system,
        home: const SplashGate(),
      ),
    );
  }
}
