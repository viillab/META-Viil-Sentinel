import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:viil_sentinel_care/features/integration/integration_readiness_page.dart';

Future<void> tapContractAction(WidgetTester tester, String key) async {
  final target = find.byKey(Key(key));
  await tester.scrollUntilVisible(
    target, 210, scrollable: find.byType(Scrollable).last,
  );
  await Scrollable.ensureVisible(tester.element(target), alignment: 0.3);
  await tester.pumpAndSettle();
  await tester.tap(target);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('validated offline contract sample expires and is not displayed', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: IntegrationReadinessPage()));
    await tapContractAction(tester, 'validate-contract-fixture');
    expect(find.byKey(const Key('contract-accepted')), findsOneWidget);

    await tester.pump(const Duration(seconds: 31));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('contract-accepted')), findsNothing);
    expect(find.text('CONTRACT SAMPLE EXPIRED · PREVIEW REMOVED'), findsOneWidget);

    await tapContractAction(tester, 'validate-contract-fixture');
    expect(find.byKey(const Key('contract-accepted')), findsOneWidget);
    expect(find.text('CONTRACT SAMPLE EXPIRED · PREVIEW REMOVED'), findsNothing);
  });

  testWidgets('background clears contract sandbox and foreground never resurrects it',
      (tester) async {
    addTearDown(() {
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    });
    await tester.pumpWidget(const MaterialApp(home: IntegrationReadinessPage()));
    await tapContractAction(tester, 'validate-contract-fixture');
    expect(find.byKey(const Key('contract-accepted')), findsOneWidget);

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('contract-accepted')), findsNothing);
    expect(find.text('CONTRACT SAMPLE CLEARED ON BACKGROUND'), findsOneWidget);

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('contract-accepted')), findsNothing);
  });

  testWidgets('unsafe-contract rejection cancels old expiry and remains visible',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(home: IntegrationReadinessPage()));
    await tapContractAction(tester, 'validate-contract-fixture');
    await tapContractAction(tester, 'reject-unsafe-contract');
    expect(find.byKey(const Key('contract-accepted')), findsNothing);
    expect(find.byKey(const Key('contract-rejected')), findsOneWidget);

    await tester.pump(const Duration(seconds: 31));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('contract-rejected')), findsOneWidget);
    expect(find.text('CONTRACT SAMPLE EXPIRED · PREVIEW REMOVED'), findsNothing);
  });
}
