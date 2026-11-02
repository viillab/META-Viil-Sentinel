import 'dart:convert';

/// Proposed read-only metadata handoff for a future *authenticated* backend.
/// Parsing a JSON field named authenticated_caregiver does NOT establish
/// authentication. This library performs zero network or device operations.
abstract final class CaregiverContractV1 {
  static const schema = 'viil.backend.caregiver_inbox.v1';
  static const maxBytes = 32 * 1024;
  static const maxAdvisories = 30;
  static const ttl = Duration(seconds: 30);
  static const futureSkew = Duration(seconds: 5);
}

class ContractRejected implements Exception {
  const ContractRejected();
  @override
  String toString() => 'Caregiver inbox rejected (redacted)';
}

final _uuid = RegExp(
  r'^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
  caseSensitive: false,
);
final _source = RegExp(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$');
final _utcIso = RegExp(
  r'^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?Z$',
);

const _envelopeKeys = {
  'schema_version', 'generated_at', 'access_scope', 'advisories',
};
const _advisoryKeys = {
  'advisory_id', 'source_id', 'occurred_at', 'stage', 'context_code',
  'meta_provenance', 'delivery_state', 'receipt_verified', 'review_state',
  'simulated', 'fall_confirmed', 'emergency_dispatch_authorized',
  'human_follow_up_required',
};
const _stages = {'edge_candidate', 'follow_up_required', 'informational_advisory'};
const _contexts = {'unknown', 'near_floor', 'wheelchair_transfer', 'rapid_descent'};
const _providers = {'none', 'mock', 'meta_model_api'};
const _deliveries = {'not_sent', 'pending', 'delivered', 'failed'};
const _reviews = {'pending', 'acknowledged', 'closed'};

bool _exact(Object? value, Set<String> keys) {
  if (value is! Map<String, dynamic> || value.length != keys.length) {
    return false;
  }
  return keys.every(value.containsKey);
}

/// Reject impossible dates rather than allowing DateTime.utc normalization
/// (which would silently accept 2026-02-30).
DateTime? _timestamp(Object? value) {
  if (value is! String) return null;
  final match = _utcIso.firstMatch(value);
  if (match == null) return null;
  final p = [
    for (var i = 1; i <= 6; i++) int.parse(match.group(i)!),
  ];
  final fractional = match.group(7);
  final millis = fractional == null ? 0 : int.parse(fractional.padRight(3, '0'));
  final date = DateTime.utc(p[0], p[1], p[2], p[3], p[4], p[5], millis);
  if (date.year != p[0] || date.month != p[1] || date.day != p[2]
      || date.hour != p[3] || date.minute != p[4]
      || date.second != p[5] || date.millisecond != millis) {
    return null;
  }
  return date;
}

/// Only vetted enum-code labels are displayed; no raw AI prose is accepted.
class SafeAdvisory {
  const SafeAdvisory({
    required this.advisoryId, required this.sourceId, required this.occurredAt,
    required this.stage, required this.contextCode, required this.metaProvenance,
    required this.deliveryState, required this.receiptVerified,
    required this.reviewState, required this.simulated,
  });
  final String advisoryId, sourceId, stage, contextCode, metaProvenance;
  final String deliveryState, reviewState;
  final DateTime occurredAt;
  final bool receiptVerified, simulated;

  String get title => switch (stage) {
    'edge_candidate' => 'Possible fall · unconfirmed Edge candidate',
    'follow_up_required' => 'Follow-up needed · assessment uncertain',
    _ => 'Informational advisory · backend-reported Meta assessment',
  };
  String get context => switch (contextCode) {
    'near_floor' => 'Person appears near floor in authorized scene',
    'wheelchair_transfer' => 'Activity may involve wheelchair transfer',
    'rapid_descent' => 'Rapid posture change was observed',
    _ => 'No reliable activity context available',
  };
  String get meta => switch (metaProvenance) {
    'mock' => 'MOCK only · no actual Meta inference',
    'meta_model_api' => 'Backend reports Meta processing · not independently verified',
    _ => 'No Meta inference reported',
  };
  String get delivery => switch (deliveryState) {
    'pending' => 'Delivery pending · not yet verified',
    'delivered' => 'Backend reports verified delivery receipt',
    'failed' => 'Delivery failed · requires human follow-up',
    _ => 'No notification dispatched',
  };
  String get review => switch (reviewState) {
    'acknowledged' => 'Backend reports acknowledged',
    'closed' => 'Backend reports closed',
    _ => 'Caregiver review pending',
  };
}

class SafeCaregiverInbox {
  SafeCaregiverInbox({required this.generatedAt, required List<SafeAdvisory> advisories})
      : advisories = List.unmodifiable(advisories);

  final DateTime generatedAt;
  final List<SafeAdvisory> advisories;

  bool freshAt(DateTime now) {
    final age = now.toUtc().difference(generatedAt);
    return age >= -CaregiverContractV1.futureSkew
        && age <= CaregiverContractV1.ttl;
  }
}

SafeAdvisory _readAdvisory(Object? value, DateTime generated) {
  if (!_exact(value, _advisoryKeys)) throw const ContractRejected();
  final v = value as Map<String, dynamic>;
  final occurrence = _timestamp(v['occurred_at']);
  final delivery = v['delivery_state'];
  final stage = v['stage'];
  final provider = v['meta_provenance'];
  if (v['advisory_id'] is! String || !_uuid.hasMatch(v['advisory_id'] as String)
      || v['source_id'] is! String || !_source.hasMatch(v['source_id'] as String)
      || occurrence == null
      || occurrence.isAfter(generated.add(CaregiverContractV1.futureSkew))
      || !_stages.contains(stage) || !_contexts.contains(v['context_code'])
      || !_providers.contains(provider) || !_deliveries.contains(delivery)
      || !_reviews.contains(v['review_state'])
      || v['simulated'] is! bool
      || v['receipt_verified'] != (delivery == 'delivered')
      || v['fall_confirmed'] != false
      || v['emergency_dispatch_authorized'] != false
      || v['human_follow_up_required'] != true
      || (stage == 'informational_advisory' && provider != 'meta_model_api')
      || (provider == 'meta_model_api' && v['simulated'] == true)
      || (stage == 'edge_candidate' && provider == 'meta_model_api')) {
    throw const ContractRejected();
  }
  return SafeAdvisory(
    advisoryId: v['advisory_id'] as String,
    sourceId: v['source_id'] as String,
    occurredAt: occurrence,
    stage: stage as String,
    contextCode: v['context_code'] as String,
    metaProvenance: provider as String,
    deliveryState: delivery as String,
    receiptVerified: v['receipt_verified'] as bool,
    reviewState: v['review_state'] as String,
    simulated: v['simulated'] as bool,
  );
}

/// Metadata-only decoder. No URL, token, HTTP request or file I/O.
SafeCaregiverInbox parseCaregiverContractJson(String jsonText) {
  if (utf8.encode(jsonText).length > CaregiverContractV1.maxBytes) {
    throw const ContractRejected();
  }
  Object? root;
  try {
    root = jsonDecode(jsonText);
  } on FormatException {
    throw const ContractRejected();
  }
  if (!_exact(root, _envelopeKeys)) throw const ContractRejected();
  final v = root as Map<String, dynamic>;
  final generated = _timestamp(v['generated_at']);
  final items = v['advisories'];
  if (v['schema_version'] != CaregiverContractV1.schema
      || v['access_scope'] != 'authenticated_caregiver'
      || generated == null || items is! List
      || items.length > CaregiverContractV1.maxAdvisories) {
    throw const ContractRejected();
  }
  final advisories = <SafeAdvisory>[];
  final ids = <String>{};
  for (final item in items) {
    final advisory = _readAdvisory(item, generated);
    if (!ids.add(advisory.advisoryId.toLowerCase())) {
      throw const ContractRejected();
    }
    advisories.add(advisory);
  }
  return SafeCaregiverInbox(generatedAt: generated, advisories: advisories);
}
