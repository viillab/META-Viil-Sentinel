import 'dart:convert';

import 'caregiver_contract_v1.dart';

/// Pure synthetic metadata used by the mobile read-only demo.
/// This is NOT an API response or a receipt of authenticated delivery.
String generatedReadOnlyInboxFixture(DateTime now, {bool expired = false}) {
  final base = DateTime.fromMillisecondsSinceEpoch(
    now.toUtc().millisecondsSinceEpoch, isUtc: true,
  ).subtract(expired ? const Duration(seconds: 31) : Duration.zero);
  Map<String, Object> fictionalAdvisory({
    required String id,
    required String source,
    required int secondsAgo,
    required String stage,
    required String context,
    required String provider,
    required String review,
  }) => {
    'advisory_id': id,
    'source_id': source,
    'occurred_at': base.subtract(Duration(seconds: secondsAgo)).toIso8601String(),
    'stage': stage,
    'context_code': context,
    'meta_provenance': provider,
    'delivery_state': 'not_sent',
    'receipt_verified': false,
    'review_state': review,
    'simulated': true,
    'fall_confirmed': false,
    'emergency_dispatch_authorized': false,
    'human_follow_up_required': true,
  };
  return jsonEncode({
    'schema_version': CaregiverContractV1.schema,
    'generated_at': base.toIso8601String(),
    // The field is part of the *shape*, NOT evidence of real authentication.
    'access_scope': 'authenticated_caregiver',
    'advisories': [
      fictionalAdvisory(
        id: 'ed76a512-508e-4afc-a716-f244012c52a1',
        source: 'demo-hallway-zone',
        secondsAgo: 1,
        stage: 'edge_candidate',
        context: 'rapid_descent',
        provider: 'none',
        review: 'pending',
      ),
      fictionalAdvisory(
        id: '6c34af85-f585-48c9-b6ce-1da88c269ce4',
        source: 'demo-transfer-zone',
        secondsAgo: 4,
        stage: 'follow_up_required',
        context: 'wheelchair_transfer',
        provider: 'mock',
        review: 'pending',
      ),
      fictionalAdvisory(
        id: '04b85db8-7bc0-4cb7-bd0b-ad798a6d82a1',
        source: 'demo-review-zone',
        secondsAgo: 6,
        stage: 'follow_up_required',
        context: 'unknown',
        provider: 'none',
        review: 'acknowledged',
      ),
    ],
  });
}
