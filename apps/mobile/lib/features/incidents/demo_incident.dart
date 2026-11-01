/// An invented, app-memory-only event. This is NOT the backend incident
/// contract, a verified fall, or an actual notification delivery receipt.
enum DemoKind { possibleFall, followUp }
enum DemoReview { pending, acknowledged }
enum DemoScenario { rapidDescent, transfer, sitting }

class DemoIncident {
  const DemoIncident({
    required this.id,
    required this.zone,
    required this.kind,
    required this.context,
    required this.occurredAt,
    this.review = DemoReview.pending,
  });

  final String id;
  final String zone;
  final DemoKind kind;
  final String context;
  final DateTime occurredAt;
  final DemoReview review;

  bool get simulated => true;
  bool get fallConfirmed => false;
  bool get notificationSent => false;
  bool get emergencyDispatchAuthorized => false;
  bool get requiresHumanFollowUp => true;

  String get title => kind == DemoKind.possibleFall
      ? 'Possible fall · unconfirmed'
      : 'Follow-up required · uncertain';

  DemoIncident copyWith({DemoReview? review}) => DemoIncident(
    id: id, zone: zone, kind: kind, context: context,
    occurredAt: occurredAt, review: review ?? this.review,
  );
}
