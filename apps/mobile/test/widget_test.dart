import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:viil_sentinel_care/app/care_app.dart';

void main() {
  testWidgets('Home is clearly simulated and shows the seeded counts', (tester) async {
    await tester.pumpWidget(const CareApp());
    expect(find.textContaining('DEMO · SIMULATED DATA ONLY'), findsOneWidget);
    expect(find.text('Care at a glance'), findsOneWidget);
    expect(find.text('Needs review'), findsOneWidget);
    expect(find.text('No devices connected · No real alerts sent'), findsOneWidget);
    expect(find.byKey(const Key('tab-alerts')), findsOneWidget);
    expect(find.byKey(const Key('tab-history')), findsOneWidget);
  });

  testWidgets('Run scenario → Alerts → Acknowledge → History → Reset', (tester) async {
    await tester.pumpWidget(const CareApp());
    await tester.tap(find.byKey(const Key('open-demo-controls')));
    await tester.pumpAndSettle();
    expect(find.text('Run a scenario'), findsOneWidget);
    await tester.tap(find.byKey(const Key('scenario-fall')));
    await tester.pump();
    expect(find.textContaining('Fictional event added'), findsOneWidget);

    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('tab-alerts')));
    await tester.pumpAndSettle();
    expect(find.text('Pending review · 2'), findsOneWidget);

    await tester.tap(find.byKey(const Key('incident-demo-3')));
    await tester.pumpAndSettle();
    expect(find.text('NOT CONFIRMED'), findsOneWidget);
    expect(find.text('MOCK ONLY · no provider call'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.byKey(const Key('acknowledge-demo')), 230,
      scrollable: find.byType(Scrollable).last,
    );
    await tester.tap(find.byKey(const Key('acknowledge-demo')));
    await tester.pump();
    expect(find.text('Already acknowledged'), findsOneWidget);

    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.text('Pending review · 1'), findsOneWidget);
    await tester.tap(find.byKey(const Key('tab-history')));
    await tester.pumpAndSettle();
    expect(find.text('Acknowledged · 2'), findsOneWidget);

    await tester.tap(find.byKey(const Key('open-demo-controls')));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.byKey(const Key('reset-demo')), 230,
      scrollable: find.byType(Scrollable).last,
    );
    await tester.tap(find.byKey(const Key('reset-demo')));
    await tester.pump();
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.text('Acknowledged · 1'), findsOneWidget);
  });

  testWidgets('Negative sitting scenario produces no event', (tester) async {
    await tester.pumpWidget(const CareApp());
    await tester.tap(find.byKey(const Key('open-demo-controls')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('scenario-sitting')));
    await tester.pump();
    expect(find.textContaining('no fall candidate generated'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('tab-alerts')));
    await tester.pumpAndSettle();
    expect(find.text('Pending review · 1'), findsOneWidget);
  });
}
