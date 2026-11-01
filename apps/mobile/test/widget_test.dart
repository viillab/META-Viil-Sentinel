import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:viil_sentinel_care/app/care_app.dart';

Future<void> tapWalkthroughAction(WidgetTester tester, int step) async {
  final action = find.byKey(Key('walkthrough-primary-$step'));
  await tester.scrollUntilVisible(
    action, 220, scrollable: find.byType(Scrollable).last,
  );
  await tester.tap(action);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('one-tap guided demo generates, reviews, acknowledges and opens history',
      (tester) async {
    await tester.pumpWidget(const CareApp());
    await tester.tap(find.byKey(const Key('start-guided-demo')));
    await tester.pumpAndSettle();
    expect(find.text('A candidate appears'), findsOneWidget);
    expect(find.textContaining('DEMO · SIMULATED DATA ONLY'), findsOneWidget);
    expect(find.text('Fall status: UNCONFIRMED'), findsOneWidget);
    expect(find.text('Push delivery: NOT SENT'), findsOneWidget);
    expect(find.text('1 / 4'), findsOneWidget);

    await tapWalkthroughAction(tester, 0);
    expect(find.text('Review before acting'), findsOneWidget);
    expect(find.text('Meta AI: MOCK ONLY · no model call'), findsOneWidget);

    await tapWalkthroughAction(tester, 1);
    expect(find.text('Acknowledge safely'), findsOneWidget);
    await tapWalkthroughAction(tester, 2);
    expect(find.text('Demo completed'), findsOneWidget);
    expect(find.textContaining('DEMO ACKNOWLEDGED'), findsWidgets);

    await tapWalkthroughAction(tester, 3);
    expect(find.text('Activity history'), findsOneWidget);
    expect(find.text('Acknowledged · 2'), findsOneWidget);
    expect(find.byKey(const Key('incident-demo-3')), findsOneWidget);
  });

  testWidgets('guide from controls returns to Home without duplicate generated events',
      (tester) async {
    await tester.pumpWidget(const CareApp());
    await tester.tap(find.byKey(const Key('open-demo-controls')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('walkthrough-from-controls')));
    await tester.pumpAndSettle();
    expect(find.text('A candidate appears'), findsOneWidget);

    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.text('Care at a glance'), findsOneWidget);
    await tester.tap(find.byKey(const Key('tab-alerts')));
    await tester.pumpAndSettle();
    expect(find.text('Pending review · 2'), findsOneWidget);
  });

  testWidgets('compact display with enlarged text keeps walkthrough usable',
      (tester) async {
    tester.view.physicalSize = const Size(320, 640);
    tester.view.devicePixelRatio = 1;
    tester.platformDispatcher.textScaleFactorTestValue = 1.4;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
      tester.platformDispatcher.clearTextScaleFactorTestValue();
    });
    await tester.pumpWidget(const CareApp());
    expect(tester.takeException(), isNull);
    await tester.tap(find.byKey(const Key('start-guided-demo')));
    await tester.pumpAndSettle();
    expect(find.text('A candidate appears'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tapWalkthroughAction(tester, 0);
    expect(find.text('Review before acting'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

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
