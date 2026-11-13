import 'package:flutter/material.dart';

import '../../theme/app_theme.dart';

class AppLogo extends StatelessWidget {
  const AppLogo({super.key, this.size = 84});
  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: withA(Colors.white, 0.18),
        border: Border.all(color: withA(Colors.white, 0.5), width: 1.5),
        boxShadow: [
          BoxShadow(color: withA(Colors.black, 0.2), blurRadius: 24, offset: const Offset(0, 10)),
        ],
      ),
      child: Icon(Icons.school_rounded, size: size * 0.5, color: Colors.white),
    );
  }
}
