import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../core/arabic_normalizer.dart';
import '../../logic/session_controller.dart';
import '../../theme/app_theme.dart';
import '../widgets/app_logo.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _id = TextEditingController();
  final _name = TextEditingController();
  final _pin = TextEditingController();
  bool _register = false;
  bool _hidePin = true;

  @override
  void dispose() {
    _id.dispose();
    _name.dispose();
    _pin.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    FocusScope.of(context).unfocus();
    await context.read<SessionController>().submit(
          register: _register,
          studentId: _id.text,
          name: _name.text,
          pin: _pin.text,
        );
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final session = context.watch<SessionController>();
    final digits = FilteringTextInputFormatter.allow(RegExp(r'[0-9٠-٩]'));

    return Scaffold(
      resizeToAvoidBottomInset: true,
      body: Container(
        decoration: const BoxDecoration(gradient: AppTheme.gradient),
        child: Stack(
          children: [
            // soft decorative circles
            Positioned(
                top: -70,
                left: -50,
                child: _circle(220, withA(Colors.white, 0.07))),
            Positioned(
                bottom: -90,
                right: -60,
                child: _circle(280, withA(AppColors.gold, 0.10))),
            SafeArea(
              child: Center(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(22),
                  child: TweenAnimationBuilder<double>(
                    tween: Tween(begin: 0, end: 1),
                    duration: const Duration(milliseconds: 700),
                    curve: Curves.easeOutCubic,
                    builder: (_, v, child) => Opacity(
                      opacity: v,
                      child: Transform.translate(
                          offset: Offset(0, 30 * (1 - v)), child: child),
                    ),
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 440),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const AppLogo(),
                          const SizedBox(height: 18),
                          const Text('المساعد الجامعي الذكي',
                              style: TextStyle(
                                  color: Colors.white,
                                  fontSize: 26,
                                  fontWeight: FontWeight.w800)),
                          const SizedBox(height: 6),
                          Text('اسأل عن التسجيل والامتحانات والإعلانات',
                              style: TextStyle(
                                  color: withA(Colors.white, 0.85), fontSize: 14)),
                          const SizedBox(height: 26),
                          Container(
                            padding: const EdgeInsets.all(22),
                            decoration: BoxDecoration(
                              color: Theme.of(context).brightness == Brightness.light
                                  ? Colors.white
                                  : const Color(0xFF151B2E),
                              borderRadius: BorderRadius.circular(28),
                              boxShadow: [
                                BoxShadow(
                                    color: withA(Colors.black, 0.25),
                                    blurRadius: 30,
                                    offset: const Offset(0, 14)),
                              ],
                            ),
                            child: Form(
                              key: _formKey,
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                children: [
                                  SegmentedButton<bool>(
                                    showSelectedIcon: false,
                                    segments: const [
                                      ButtonSegment(value: false, label: Text('تسجيل الدخول')),
                                      ButtonSegment(value: true, label: Text('حساب جديد')),
                                    ],
                                    selected: {_register},
                                    onSelectionChanged: (s) {
                                      context.read<SessionController>().clearError();
                                      setState(() => _register = s.first);
                                    },
                                  ),
                                  const SizedBox(height: 18),
                                  TextFormField(
                                    controller: _id,
                                    keyboardType: TextInputType.number,
                                    inputFormatters: [digits],
                                    textInputAction: TextInputAction.next,
                                    decoration: const InputDecoration(
                                      labelText: 'الرقم الجامعي',
                                      prefixIcon: Icon(Icons.badge_outlined),
                                    ),
                                    validator: (v) {
                                      final x = ArabicNormalizer.digitsToWestern((v ?? '').trim());
                                      return RegExp(r'^\d{5,12}$').hasMatch(x)
                                          ? null
                                          : 'أدخل رقماً جامعياً صحيحاً';
                                    },
                                  ),
                                  AnimatedSize(
                                    duration: const Duration(milliseconds: 300),
                                    curve: Curves.easeOutCubic,
                                    alignment: Alignment.topCenter,
                                    child: _register
                                        ? Padding(
                                            padding: const EdgeInsets.only(top: 14),
                                            child: TextFormField(
                                              controller: _name,
                                              textInputAction: TextInputAction.next,
                                              decoration: const InputDecoration(
                                                labelText: 'الاسم',
                                                prefixIcon: Icon(Icons.person_outline_rounded),
                                              ),
                                              validator: (v) => (v ?? '').trim().length < 2
                                                  ? 'أدخل اسمك'
                                                  : null,
                                            ),
                                          )
                                        : const SizedBox(width: double.infinity),
                                  ),
                                  const SizedBox(height: 14),
                                  TextFormField(
                                    controller: _pin,
                                    obscureText: _hidePin,
                                    keyboardType: TextInputType.number,
                                    inputFormatters: [digits, LengthLimitingTextInputFormatter(6)],
                                    onFieldSubmitted: (_) => _submit(),
                                    decoration: InputDecoration(
                                      labelText: 'الرمز السري (4 إلى 6 أرقام)',
                                      prefixIcon: const Icon(Icons.lock_outline_rounded),
                                      suffixIcon: IconButton(
                                        icon: Icon(_hidePin
                                            ? Icons.visibility_outlined
                                            : Icons.visibility_off_outlined),
                                        onPressed: () => setState(() => _hidePin = !_hidePin),
                                      ),
                                    ),
                                    validator: (v) {
                                      final x = ArabicNormalizer.digitsToWestern((v ?? '').trim());
                                      return RegExp(r'^\d{4,6}$').hasMatch(x)
                                          ? null
                                          : 'من 4 إلى 6 أرقام';
                                    },
                                  ),
                                  AnimatedSwitcher(
                                    duration: const Duration(milliseconds: 250),
                                    child: session.error == null
                                        ? const SizedBox(key: ValueKey('noerr'), height: 14)
                                        : Container(
                                            key: ValueKey(session.error),
                                            margin: const EdgeInsets.only(top: 14, bottom: 2),
                                            padding: const EdgeInsets.all(12),
                                            decoration: BoxDecoration(
                                              color: withA(cs.error, 0.10),
                                              borderRadius: BorderRadius.circular(12),
                                            ),
                                            child: Row(children: [
                                              Icon(Icons.error_outline_rounded,
                                                  color: cs.error, size: 20),
                                              const SizedBox(width: 8),
                                              Expanded(
                                                  child: Text(session.error!,
                                                      style: TextStyle(color: cs.error))),
                                            ]),
                                          ),
                                  ),
                                  const SizedBox(height: 10),
                                  FilledButton(
                                    onPressed: session.busy ? null : _submit,
                                    child: session.busy
                                        ? const SizedBox(
                                            width: 22,
                                            height: 22,
                                            child: CircularProgressIndicator(
                                                strokeWidth: 2.4, color: Colors.white))
                                        : Text(_register ? 'إنشاء الحساب' : 'دخول'),
                                  ),
                                ],
                              ),
                            ),
                          ),
                          const SizedBox(height: 18),
                          Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(Icons.shield_outlined, size: 16, color: withA(Colors.white, 0.8)),
                              const SizedBox(width: 6),
                              Text('بياناتك ومحادثاتك محفوظة على جهازك فقط',
                                  style: TextStyle(color: withA(Colors.white, 0.85), fontSize: 12.5)),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _circle(double size, Color color) => Container(
        width: size,
        height: size,
        decoration: BoxDecoration(shape: BoxShape.circle, color: color),
      );
}
