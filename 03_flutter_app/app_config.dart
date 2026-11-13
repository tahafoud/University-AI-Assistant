class AppConfig {
  /// Server that hosts announcements.json and media/ (output of the Python
  /// ingestion). Android emulator -> your PC is 10.0.2.2.
  /// Override at build time: --dart-define=API_BASE=https://example.edu
  static const String baseUrl =
      String.fromEnvironment('API_BASE', defaultValue: 'http://10.0.2.2:8000');
  static const String announcementsPath = '/announcements.json';
  static String mediaUrl(String name) =>
      '$baseUrl/media/${Uri.encodeComponent(name)}';

  static const double confidenceThreshold = 0.60;
  static const Duration syncTimeout = Duration(seconds: 8);
  static const Duration minSyncInterval = Duration(minutes: 5);
}
