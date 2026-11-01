import 'package:flutter_test/flutter_test.dart';
import 'package:viil_sentinel_care/features/incidents/demo_controller.dart';
import 'package:viil_sentinel_care/features/incidents/demo_incident.dart';

void main() {
  final sampleTime = DateTime.utc(2026, 11, 2, 9, 0);

  test('seeded demo data is fictional and has no delivery authority', () {
    final controller = DemoController(clock: () => sampleTime);
    expect(controller.events.length, 2);
    expect(controller.pendingCount, 1);
    expect(controller.reviewedCount, 1);
    for (final incident in controller.events) {
      expect(incident.simulated, true);
      expect(incident.fallConfirmed, false);
      expect(incident.notificationSent, false);
      expect(incident.emergencyDispatchAuthorized, false);
      expect(incident.requiresHumanFollowUp, true);
    }
    controller.dispose();
  });

  test('positive scenarios generate local events; sitting abstains', () {
    final controller = DemoController(clock: () => sampleTime);
    expect(controller.simulate(DemoScenario.sitting), isNull);
    expect(controller.pendingCount, 1);
    final fall = controller.simulate(DemoScenario.rapidDescent)!;
    expect(fall.kind, DemoKind.possibleFall);
    expect(fall.id, 'demo-3');
    expect(fall.occurredAt, sampleTime);
    final uncertain = controller.simulate(DemoScenario.transfer)!;
    expect(uncertain.kind, DemoKind.followUp);
    expect(controller.pendingCount, 3);
    expect(controller.events.first.id, uncertain.id);
    controller.dispose();
  });

  test('acknowledgement only changes in-memory demo review state', () {
    final controller = DemoController(clock: () => sampleTime);
    final source = controller.pending.single;
    expect(controller.acknowledge(source.id), true);
    expect(controller.pendingCount, 0);
    expect(controller.reviewedCount, 2);
    expect(controller.acknowledge(source.id), false);
    expect(controller.acknowledge('not-a-demo-event'), false);
    final now = controller.byId(source.id)!;
    expect(now.review, DemoReview.acknowledged);
    expect(now.simulated, true);
    expect(now.notificationSent, false);
    expect(now.fallConfirmed, false);
    controller.reset();
    expect(controller.pendingCount, 1);
    expect(controller.reviewedCount, 1);
    controller.dispose();
  });

  test('returned event lists cannot mutate repository', () {
    final controller = DemoController(clock: () => sampleTime);
    expect(
      () => controller.events.clear(),
      throwsUnsupportedError,
    );
    expect(
      () => controller.pending.removeAt(0),
      throwsUnsupportedError,
    );
    controller.dispose();
  });
}
