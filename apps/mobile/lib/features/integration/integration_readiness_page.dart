import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import '../../core/care_theme.dart';
import '../../shared/care_widgets.dart';
import 'caregiver_contract_v1.dart';
import 'readonly_inbox_preview_page.dart';

/// Local *generated* metadata. The access_scope field is intentionally
/// present for shape testing but never constitutes an authenticated session.
String generatedCaregiverFixture(DateTime now, {bool unsafe = false}) {
  final utc = DateTime.fromMillisecondsSinceEpoch(
    now.toUtc().millisecondsSinceEpoch, isUtc: true,
  );
  final advisory = <String, Object>{
    'advisory_id': 'ed76a512-508e-4afc-a716-f244012c52a1',
    'source_id': 'demo-hallway-zone',
    'occurred_at': utc.subtract(const Duration(seconds: 2)).toIso8601String(),
    'stage': 'edge_candidate',
    'context_code': 'rapid_descent',
    'meta_provenance': 'none',
    'delivery_state': 'not_sent',
    'receipt_verified': false,
    'review_state': 'pending',
    'simulated': true,
    'fall_confirmed': false,
    'emergency_dispatch_authorized': false,
    'human_follow_up_required': true,
  };
  if (unsafe) {
    advisory['image_url'] = 'not-permitted-in-contract';
  }
  return jsonEncode({
    'schema_version': CaregiverContractV1.schema,
    'generated_at': utc.toIso8601String(),
    'access_scope': 'authenticated_caregiver',
    'advisories': [advisory],
  });
}

class IntegrationReadinessPage extends StatefulWidget {
  const IntegrationReadinessPage({super.key});

  @override
  State<IntegrationReadinessPage> createState() => _IntegrationReadinessPageState();
}

class _IntegrationReadinessPageState extends State<IntegrationReadinessPage>
    with WidgetsBindingObserver {
  SafeCaregiverInbox? _preview;
  Timer? _expiryTimer;
  bool _rejectedUnsafe = false;
  bool _failed = false;
  bool _sampleExpired = false;
  bool _clearedInBackground = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  void _clearSample({bool expired = false, bool background = false}) {
    _expiryTimer?.cancel();
    _expiryTimer = null;
    if (!mounted) return;
    setState(() {
      _preview = null;
      _rejectedUnsafe = false;
      _failed = false;
      _sampleExpired = expired;
      _clearedInBackground = background;
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // A sandbox snapshot is never kept when the app is not foregrounded.
    if (state != AppLifecycleState.resumed) _clearSample(background: true);
  }

  void _scheduleExpiry(SafeCaregiverInbox sample) {
    final expiresAt = sample.generatedAt
        .add(CaregiverContractV1.ttl)
        .add(const Duration(milliseconds: 1));
    final delay = expiresAt.difference(DateTime.now());
    _expiryTimer = Timer(delay.isNegative ? Duration.zero : delay, () {
      _clearSample(expired: true);
    });
  }

  @override
  void dispose() {
    _expiryTimer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  void _validateExample() {
    _expiryTimer?.cancel();
    _expiryTimer = null;
    try {
      final actual = parseCaregiverContractJson(
        generatedCaregiverFixture(DateTime.now()),
      );
      final fresh = actual.freshAt(DateTime.now());
      setState(() {
        _preview = fresh ? actual : null;
        _rejectedUnsafe = false;
        _failed = false;
        _sampleExpired = !fresh;
        _clearedInBackground = false;
      });
      if (fresh) _scheduleExpiry(actual);
    } on ContractRejected {
      setState(() {
        _preview = null;
        _rejectedUnsafe = false;
        _failed = true;
        _sampleExpired = false;
        _clearedInBackground = false;
      });
    }
  }

  void _rejectUnsafe() {
    _expiryTimer?.cancel();
    _expiryTimer = null;
    var rejected = false;
    try {
      parseCaregiverContractJson(
        generatedCaregiverFixture(DateTime.now(), unsafe: true),
      );
    } on ContractRejected {
      rejected = true;
    }
    setState(() {
      _preview = null;
      _rejectedUnsafe = rejected;
      _failed = !rejected;
      _sampleExpired = false;
      _clearedInBackground = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    // The validity check also protects resumed frames before the timer fires.
    final freshPreview = _preview != null && _preview!.freshAt(DateTime.now())
        ? _preview
        : null;
    return Scaffold(
    appBar: AppBar(title: const Text('Mobile integration contract')),
    body: CenteredPage(children: [
      const DemoNotice(),
      const SizedBox(height: 20),
      Text('Backend readiness', style: Theme.of(context).textTheme.headlineMedium),
      const SizedBox(height: 7),
      const Text(
        'Read-only, offline contract inspection. The app does not log in, '
        'fetch inbox data, infer incidents, or deliver alerts.',
        style: TextStyle(color: CareColors.muted, fontSize: 12),
      ),
      const SizedBox(height: 19),
      const Card(
        margin: EdgeInsets.zero,
        child: Padding(
          padding: EdgeInsets.all(19),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              StatusPill(text: 'LIVE INTEGRATION DISABLED'),
              SizedBox(height: 14),
              _ReadinessRow('Mobile codec', 'Metadata-only v1 validation'),
              _ReadinessRow('Backend auth / RBAC', 'NOT VERIFIED'),
              _ReadinessRow('Authenticated inbox API', 'NOT CONNECTED'),
              _ReadinessRow('Meta provider', 'NOT CONNECTED'),
              _ReadinessRow('Push delivery', 'DISABLED'),
              _ReadinessRow('Emergency actions', 'DISABLED'),
            ],
          ),
        ),
      ),
      const SizedBox(height: 20),
      const SectionHeader('Contract sandbox'),
      const SizedBox(height: 10),
      const Text(
        'Schema: viil.backend.caregiver_inbox.v1. The field '
        'access_scope=authenticated_caregiver is just sample text, '
        'not authentication evidence. This test never enables Live Mode.',
        style: TextStyle(color: CareColors.muted, fontSize: 12),
      ),
      const SizedBox(height: 16),
      FilledButton.icon(
        key: const Key('open-readonly-inbox-preview'),
        onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
          builder: (_) => const ReadOnlyInboxPreviewPage(),
        )),
        icon: const Icon(Icons.inbox_outlined),
        label: const Text('Open read-only Inbox Preview'),
      ),
      const SizedBox(height: 10),
      OutlinedButton.icon(
        key: const Key('validate-contract-fixture'),
        onPressed: _validateExample,
        icon: const Icon(Icons.verified_user_outlined),
        label: const Text('Validate generated inbox sample'),
      ),
      const SizedBox(height: 10),
      OutlinedButton.icon(
        key: const Key('reject-unsafe-contract'),
        onPressed: _rejectUnsafe,
        icon: const Icon(Icons.gpp_bad_outlined),
        label: const Text('Test rejection of unsafe image field'),
      ),
      if (_sampleExpired || (_preview != null && freshPreview == null)) ...[
        const SizedBox(height: 18),
        const StatusPill(text: 'CONTRACT SAMPLE EXPIRED · PREVIEW REMOVED'),
      ],
      if (_clearedInBackground) ...[
        const SizedBox(height: 18),
        const StatusPill(text: 'CONTRACT SAMPLE CLEARED ON BACKGROUND'),
      ],
      if (freshPreview != null) ...[
        const SizedBox(height: 18),
        Card(
          key: const Key('contract-accepted'),
          margin: EdgeInsets.zero,
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const StatusPill(
                  text: 'SYNTHETIC CONTRACT VALID · NOT AUTHENTICATED',
                  acknowledged: true,
                ),
                const SizedBox(height: 14),
                Text('${freshPreview.advisories.length} fictional advisory',
                    style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 13),
                for (final item in freshPreview.advisories) ...[
                  Text(item.title,
                    style: const TextStyle(
                      fontWeight: FontWeight.w800, color: CareColors.ink,
                    )),
                  const SizedBox(height: 6),
                  Text(item.context, style: const TextStyle(
                    color: CareColors.muted, fontSize: 12,
                  )),
                  const SizedBox(height: 6),
                  Text(item.meta, style: const TextStyle(
                    color: CareColors.muted, fontSize: 12,
                  )),
                  const SizedBox(height: 6),
                  Text(item.delivery, style: const TextStyle(
                    color: CareColors.muted, fontSize: 12,
                  )),
                ],
                const SizedBox(height: 8),
                const Text('No backend session or real notification was verified.',
                  style: TextStyle(color: CareColors.muted, fontSize: 11)),
              ],
            ),
          ),
        ),
      ],
      if (_rejectedUnsafe) ...[
        const SizedBox(height: 18),
        const Card(
          key: Key('contract-rejected'),
          margin: EdgeInsets.zero,
          child: Padding(
            padding: EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                StatusPill(text: 'UNSAFE PAYLOAD REJECTED', acknowledged: true),
                SizedBox(height: 10),
                Text('Extra image field is not allowed. '
                  'No payload content is shown or retained.',
                  style: TextStyle(fontSize: 12)),
              ],
            ),
          ),
        ),
      ],
      if (_failed) ...[
        const SizedBox(height: 15),
        const Text('Contract verification failed (redacted). '
          'Live mode stays disabled.',
          style: TextStyle(color: CareColors.amber, fontSize: 12)),
      ],
      const SizedBox(height: 18),
      const Text(
        'Only an independently authorized Member 2 backend can supply '
        'actual caregiver advisories. Matching a JSON schema never '
        'grants access or proves delivery. No patient monitoring is active.',
        style: TextStyle(color: CareColors.muted, fontSize: 11, height: 1.6),
      ),
    ]),
    );
  }
}

class _ReadinessRow extends StatelessWidget {
  const _ReadinessRow(this.name, this.value);
  final String name;
  final String value;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 8),
    child: Row(
      children: [
        Expanded(child: Text(name, style: const TextStyle(
          color: CareColors.muted, fontSize: 11,
        ))),
        Flexible(child: Text(value, textAlign: TextAlign.right,
          style: const TextStyle(
            color: CareColors.ink, fontWeight: FontWeight.w800, fontSize: 10,
          ))),
      ],
    ),
  );
}
