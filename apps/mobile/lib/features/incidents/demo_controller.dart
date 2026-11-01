import 'package:flutter/foundation.dart';
import 'demo_incident.dart';

/// No HTTP, storage, camera, Meta, push, device permissions or timers.
/// Every mutation is explicitly local to this single demo app session.
class DemoController extends ChangeNotifier {
  DemoController({DateTime Function()? clock}) : _clock = clock ?? DateTime.now {
    reset();
  }

  final DateTime Function() _clock;
  /// Upper bound for all fictional in-memory records. No persistent storage.
  static const maxDemoEvents = 32;

  final List<DemoIncident> _events = [];
  int _sequence = 3;
  String? _guidedEventId;

  List<DemoIncident> get events => List.unmodifiable(_events);
  List<DemoIncident> get pending => List.unmodifiable(
    _events.where((event) => event.review == DemoReview.pending),
  );
  List<DemoIncident> get acknowledged => List.unmodifiable(
    _events.where((event) => event.review == DemoReview.acknowledged),
  );
  int get pendingCount => pending.length;
  int get reviewedCount => acknowledged.length;

  DemoIncident? byId(String id) {
    for (final event in _events) {
      if (event.id == id) return event;
    }
    return null;
  }

  /// Returns null for a sitting/non-candidate scenario.
  DemoIncident? simulate(DemoScenario scenario) {
    if (scenario == DemoScenario.sitting) return null;
    final event = DemoIncident(
      id: 'demo-${_sequence++}',
      zone: scenario == DemoScenario.rapidDescent ? 'Hallway Zone' : 'Transfer Zone',
      kind: scenario == DemoScenario.rapidDescent
          ? DemoKind.possibleFall : DemoKind.followUp,
      context: scenario == DemoScenario.rapidDescent
          ? 'Invented rapid posture change' : 'Invented wheelchair transfer',
      occurredAt: _clock(),
    );
    _events.insert(0, event);
    if (_events.length > maxDemoEvents) {
      _events.removeRange(maxDemoEvents, _events.length);
    }
    notifyListeners();
    return event;
  }

  /// Reuse the single pending guided event rather than duplicating it.
  /// On replay after acknowledgement, replace only the old guided sample:
  /// other manually generated scenarios and their review state are retained.
  DemoIncident startOrResumeGuidedDemo() {
    final previousId = _guidedEventId;
    if (previousId != null) {
      final previous = byId(previousId);
      if (previous != null && previous.review == DemoReview.pending) {
        return previous;
      }
      _events.removeWhere((event) => event.id == previousId);
      _guidedEventId = null;
    }
    final next = simulate(DemoScenario.rapidDescent)!;
    _guidedEventId = next.id;
    return next;
  }

  bool acknowledge(String id) {
    final index = _events.indexWhere((e) => e.id == id);
    if (index < 0 || _events[index].review == DemoReview.acknowledged) {
      return false;
    }
    _events[index] = _events[index].copyWith(review: DemoReview.acknowledged);
    notifyListeners();
    return true;
  }

  void reset() {
    final now = _clock();
    _events
      ..clear()
      ..addAll([
        DemoIncident(
          id: 'demo-001', zone: 'Hallway Zone',
          kind: DemoKind.possibleFall,
          context: 'Invented rapid posture change',
          occurredAt: now.subtract(const Duration(minutes: 4)),
        ),
        DemoIncident(
          id: 'demo-002', zone: 'Transfer Zone',
          kind: DemoKind.followUp,
          context: 'Invented wheelchair transfer',
          occurredAt: now.subtract(const Duration(minutes: 26)),
          review: DemoReview.acknowledged,
        ),
      ]);
    _sequence = 3;
    _guidedEventId = null;
    notifyListeners();
  }
}
