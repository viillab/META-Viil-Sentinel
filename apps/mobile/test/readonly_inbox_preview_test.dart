import 'package:flutter_test/flutter_test.dart';
import 'package:viil_sentinel_care/features/integration/caregiver_contract_v1.dart';
import 'package:viil_sentinel_care/features/integration/readonly_inbox_fixture.dart';

void main() {
  final clock = DateTime.utc(2026, 11, 2, 8, 0, 0);

  test('generated inbox preview has 3 unique fictional, read-only metadata items', () {
    final inbox = parseCaregiverContractJson(generatedReadOnlyInboxFixture(clock));
    expect(inbox.freshAt(clock), true);
    expect(inbox.advisories.length, 3);
    expect(inbox.advisories.map((a) => a.advisoryId).toSet().length, 3);
    expect(inbox.advisories.where((a) => a.reviewState == 'pending').length, 2);
    expect(inbox.advisories.where((a) => a.reviewState == 'acknowledged').length, 1);
    for (final a in inbox.advisories) {
      expect(a.simulated, true);
      expect(a.deliveryState, 'not_sent');
      expect(a.receiptVerified, false);
      expect(a.metaProvenance == 'mock' || a.metaProvenance == 'none', true);
    }
    expect(() => inbox.advisories.clear(), throwsUnsupportedError);
  });

  test('expired fixture is syntactically valid but rejected by freshness gate', () {
    final inbox = parseCaregiverContractJson(
      generatedReadOnlyInboxFixture(clock, expired: true),
    );
    expect(inbox.advisories.length, 3);
    expect(inbox.freshAt(clock), false);
    final refreshed = parseCaregiverContractJson(
      generatedReadOnlyInboxFixture(clock),
    );
    expect(refreshed.freshAt(clock), true);
    expect(refreshed.freshAt(clock.add(const Duration(seconds: 31))), false);
  });
}
