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

  test('guided start resumes pending event without creating duplicates', () {
    final controller = DemoController(clock: () => sampleTime);
    final first = controller.startOrResumeGuidedDemo();
    expect(first.id, 'demo-3');
    expect(controller.events.length, 3);
    expect(controller.startOrResumeGuidedDemo().id, first.id);
    expect(controller.events.where((event) => event.id == first.id).length, 1);
    expect(controller.pendingCount, 2);
    controller.dispose();
  });

  test('guided replay replaces only prior guided event and preserves manual events', () {
    final controller = DemoController(clock: () => sampleTime);
    final manuallyCreated = controller.simulate(DemoScenario.transfer)!;
    final first = controller.startOrResumeGuidedDemo();
    expect(controller.acknowledge(first.id), true);
    final replay = controller.startOrResumeGuidedDemo();
    expect(replay.id, isNot(first.id));
    expect(replay.review, DemoReview.pending);
    expect(controller.byId(first.id), isNull);
    expect(controller.byId(manuallyCreated.id), isNotNull);
    expect(controller.events.length, 4);
    expect(controller.pendingCount, 3);
    expect(controller.reviewedCount, 1);
    expect(controller.startOrResumeGuidedDemo().id, replay.id);
    controller.reset();
    expect(controller.events.length, 2);
    expect(controller.startOrResumeGuidedDemo().id, 'demo-3');
    controller.dispose();
  });

  test('rapid fictional scenario creation is bounded without id reuse', () {
    final controller = DemoController(clock: () => sampleTime);
    for (var i = 0; i < 120; i++) {
      controller.simulate(DemoScenario.rapidDescent);
      expect(controller.events.length, lessThanOrEqualTo(DemoController.maxDemoEvents));
    }
    expect(controller.events.length, DemoController.maxDemoEvents);
    expect(controller.events.map((event) => event.id).toSet().length,
      controller.events.length);
    expect(controller.events.first.id, 'demo-122');
    expect(controller.simulate(DemoScenario.sitting), isNull);
    expect(controller.events.length, DemoController.maxDemoEvents);
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
