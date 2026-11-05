import 'package:flutter/material.dart';

abstract final class CareColors {
  static const navy = Color(0xFF132D4F);
  static const blue = Color(0xFF366DE7);
  static const ink = Color(0xFF1A3150);
  static const muted = Color(0xFF697D97);
  static const background = Color(0xFFF4F7FC);
  static const line = Color(0xFFDFE8F4);
  static const amber = Color(0xFFD99027);
  static const teal = Color(0xFF148F85);
}

ThemeData buildCareTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: CareColors.blue,
    brightness: Brightness.light,
    surface: Colors.white,
  );
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: CareColors.background,
    appBarTheme: const AppBarTheme(
      backgroundColor: CareColors.background,
      foregroundColor: CareColors.ink,
      elevation: 0,
      scrolledUnderElevation: 0,
    ),
    cardTheme: CardThemeData(
      color: Colors.white,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: const BorderSide(color: CareColors.line),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: CareColors.blue,
        foregroundColor: Colors.white,
        minimumSize: const Size(0, 50),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(0, 48),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: Colors.white,
      indicatorColor: const Color(0xFFE7F0FF),
      labelTextStyle: WidgetStateProperty.all(
        const TextStyle(fontSize: 11, fontWeight: FontWeight.w700),
      ),
    ),
    textTheme: const TextTheme(
      headlineMedium: TextStyle(
        color: CareColors.ink, fontSize: 28, fontWeight: FontWeight.w800,
        letterSpacing: -0.7,
      ),
      headlineSmall: TextStyle(
        color: CareColors.ink, fontSize: 21, fontWeight: FontWeight.w800,
      ),
      titleLarge: TextStyle(
        color: CareColors.ink, fontSize: 17, fontWeight: FontWeight.w800,
      ),
      bodyMedium: TextStyle(
        color: CareColors.ink, height: 1.5, fontSize: 13,
      ),
    ),
  );
}
