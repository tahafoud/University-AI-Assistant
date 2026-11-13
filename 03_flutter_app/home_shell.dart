import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../logic/announcements_controller.dart';
import '../../logic/chat_controller.dart';
import '../../logic/session_controller.dart';
import '../../theme/app_theme.dart';
import 'announcements_screen.dart';
import 'chat_screen.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});
  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> with WidgetsBindingObserver {
  int _tab = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // Background refresh at startup; UI already shows local data.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) context.read<AnnouncementsController>().sync();
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && mounted) {
      context.read<AnnouncementsController>().sync();
    }
  }

  @override
  Widget build(BuildContext context) {
    final chatTab = _tab == 0;
    return Scaffold(
      drawer: _ConversationsDrawer(onPicked: () => setState(() => _tab = 0)),
      appBar: AppBar(
        title: Text(chatTab ? 'المساعد الجامعي' : 'إعلانات الجامعة'),
        actions: [
          if (chatTab)
            IconButton(
              tooltip: 'محادثة جديدة',
              icon: const Icon(Icons.edit_square),
              onPressed: () => context.read<ChatController>().newChat(),
            ),
        ],
      ),
      body: IndexedStack(
        index: _tab,
        children: const [ChatScreen(), AnnouncementsScreen()],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: const [
          NavigationDestination(
              icon: Icon(Icons.chat_bubble_outline_rounded),
              selectedIcon: Icon(Icons.chat_bubble_rounded),
              label: 'المحادثة'),
          NavigationDestination(
              icon: Icon(Icons.campaign_outlined),
              selectedIcon: Icon(Icons.campaign_rounded),
              label: 'الإعلانات'),
        ],
      ),
    );
  }
}

class _ConversationsDrawer extends StatelessWidget {
  const _ConversationsDrawer({required this.onPicked});
  final VoidCallback onPicked;

  @override
  Widget build(BuildContext context) {
    final chat = context.watch<ChatController>();
    final student = chat.student;
    final cs = Theme.of(context).colorScheme;

    return Drawer(
      child: Column(
        children: [
          Container(
            width: double.infinity,
            padding: EdgeInsets.fromLTRB(
                20, MediaQuery.paddingOf(context).top + 20, 20, 20),
            decoration: const BoxDecoration(gradient: AppTheme.gradient),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                CircleAvatar(
                  radius: 28,
                  backgroundColor: withA(Colors.white, 0.2),
                  child: Text(
                    student.name.isEmpty ? '?' : student.name.characters.first,
                    style: const TextStyle(
                        color: Colors.white, fontSize: 24, fontWeight: FontWeight.w800),
                  ),
                ),
                const SizedBox(height: 12),
                Text(student.name,
                    style: const TextStyle(
                        color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700)),
                Text('الرقم الجامعي: ${student.id}',
                    style: TextStyle(color: withA(Colors.white, 0.85), fontSize: 13)),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(14),
            child: FilledButton.icon(
              onPressed: () {
                chat.newChat();
                Navigator.pop(context);
                onPicked();
              },
              icon: const Icon(Icons.add_rounded),
              label: const Text('محادثة جديدة'),
            ),
          ),
          Expanded(
            child: chat.conversations.isEmpty
                ? Center(
                    child: Text('لا توجد محادثات سابقة', style: TextStyle(color: cs.outline)))
                : ListView.builder(
                    itemCount: chat.conversations.length,
                    itemBuilder: (_, i) {
                      final c = chat.conversations[i];
                      return ListTile(
                        selected: c.id == chat.activeId,
                        selectedTileColor: withA(cs.primary, 0.10),
                        leading: const Icon(Icons.chat_bubble_outline_rounded),
                        title: Text(c.title, maxLines: 1, overflow: TextOverflow.ellipsis),
                        onTap: () {
                          chat.open(c.id);
                          Navigator.pop(context);
                          onPicked();
                        },
                        trailing: IconButton(
                          icon: const Icon(Icons.delete_outline_rounded),
                          onPressed: () => _confirmDelete(context, chat, c.id),
                        ),
                      );
                    },
                  ),
          ),
          const Divider(height: 1),
          ListTile(
            leading: const Icon(Icons.logout_rounded),
            title: const Text('تسجيل الخروج'),
            onTap: () => context.read<SessionController>().logout(),
          ),
          SizedBox(height: MediaQuery.paddingOf(context).bottom),
        ],
      ),
    );
  }

  Future<void> _confirmDelete(BuildContext context, ChatController chat, int id) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('حذف المحادثة؟'),
        content: const Text('سيتم حذف المحادثة ورسائلها نهائياً من جهازك.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('إلغاء')),
          FilledButton(
            style: FilledButton.styleFrom(minimumSize: const Size(90, 44)),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('حذف'),
          ),
        ],
      ),
    );
    if (ok == true) await chat.delete(id);
  }
}
