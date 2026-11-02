import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/care_theme.dart';
import '../../shared/care_widgets.dart';
import 'caregiver_contract_v1.dart';
import 'readonly_inbox_fixture.dart';

/// Read-only fictional inbox. Never merges into the in-memory Alerts queue.
/// No API client, session, live route, acknowledgement or push capabilities.
class ReadOnlyInboxPreviewPage extends StatefulWidget {
  const ReadOnlyInboxPreviewPage({super.key});

  @override
  State<ReadOnlyInboxPreviewPage> createState() => _ReadOnlyInboxPreviewPageState();
}

class _ReadOnlyInboxPreviewPageState extends State<ReadOnlyInboxPreviewPage>
    with WidgetsBindingObserver {
  SafeCaregiverInbox? _snapshot;
  String? _selectedId;
  Timer? _expiry;
  bool _expired = false;
  bool _clearedForPrivacy = false;
  bool _invalid = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  void _clearSnapshot({
    bool expired = false,
    bool hidden = false,
    bool invalid = false,
  }) {
    _expiry?.cancel();
    _expiry = null;
    if (!mounted) return;
    setState(() {
      _snapshot = null;
      _selectedId = null;
      _expired = expired;
      _clearedForPrivacy = hidden;
      _invalid = invalid;
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Privacy-first: forget even fictional metadata upon backgrounding.
    if (state != AppLifecycleState.resumed) _clearSnapshot(hidden: true);
  }

  void _load({bool expired = false}) {
    _expiry?.cancel();
    final now = DateTime.now();
    SafeCaregiverInbox value;
    try {
      value = parseCaregiverContractJson(
        generatedReadOnlyInboxFixture(now, expired: expired),
      );
    } on ContractRejected {
      _clearSnapshot(invalid: true);
      return;
    }
    if (!value.freshAt(now)) {
      _clearSnapshot(expired: true);
      return;
    }
    setState(() {
      _snapshot = value;
      _selectedId = value.advisories.isEmpty ? null : value.advisories.first.advisoryId;
      _expired = false;
      _clearedForPrivacy = false;
      _invalid = false;
    });
    // The snapshot is cleared automatically; no polling or network access.
    final expiresAt = value.generatedAt
        .add(CaregiverContractV1.ttl)
        .add(const Duration(milliseconds: 1));
    final delay = expiresAt.difference(DateTime.now());
    _expiry = Timer(delay.isNegative ? Duration.zero : delay, () {
      _clearSnapshot(expired: true);
    });
  }

  @override
  void dispose() {
    _expiry?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // A resumed route never silently retains an expired sample.
    final data = _snapshot;
    final fresh = data != null && data.freshAt(DateTime.now());
    final items = fresh ? data.advisories : <SafeAdvisory>[];
    final pending = items.where((a) => a.reviewState == 'pending').length;
    SafeAdvisory? selected;
    for (final a in items) {
      if (a.advisoryId == _selectedId) {
        selected = a;
        break;
      }
    }
    if (selected == null && items.isNotEmpty) selected = items.first;
    return Scaffold(
      appBar: AppBar(title: const Text('Caregiver Inbox preview')),
      body: CenteredPage(children: [
        const DemoNotice(),
        const SizedBox(height: 19),
        Text('Caregiver inbox', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 5),
        const Text(
          'Offline read-only preview · entirely fictional metadata',
          style: TextStyle(color: CareColors.muted, fontSize: 12),
        ),
        const SizedBox(height: 15),
        Container(
          key: const Key('inbox-preview-banner'),
          padding: const EdgeInsets.all(15),
          decoration: BoxDecoration(
            color: const Color(0xFFFFF5E7),
            borderRadius: BorderRadius.circular(15),
            border: Border.all(color: const Color(0xFFECD6AC)),
          ),
          child: const Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.visibility_off_outlined, color: Color(0xFF98651F)),
              SizedBox(width: 11),
              Expanded(child: Text(
                'SAMPLE ONLY · NO AUTHENTICATED BACKEND\n'
                'Viewing cannot acknowledge, verify a fall or send a notification.',
                style: TextStyle(color: Color(0xFF805520), fontSize: 11,
                  fontWeight: FontWeight.w800, height: 1.6),
              )),
            ],
          ),
        ),
        const SizedBox(height: 17),
        FilledButton.icon(
          key: const Key('inbox-load-sample'),
          onPressed: _load,
          icon: const Icon(Icons.refresh),
          label: const Text('Load fresh fictional inbox'),
        ),
        const SizedBox(height: 10),
        OutlinedButton.icon(
          key: const Key('inbox-test-stale'),
          onPressed: () => _load(expired: true),
          icon: const Icon(Icons.timer_off_outlined),
          label: const Text('Simulate expired snapshot'),
        ),
        const SizedBox(height: 14),
        if (!fresh) Card(
          key: const Key('inbox-unavailable'),
          margin: EdgeInsets.zero,
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const StatusPill(text: 'NO ACTIVE INBOX DATA'),
                const SizedBox(height: 12),
                Text(
                  _expired || (data != null && !fresh)
                      ? 'STALE DATA BLOCKED · reload fictional sample'
                      : _invalid
                          ? 'INVALID CONTRACT · no data displayed'
                          : _clearedForPrivacy
                              ? 'PREVIEW CLEARED ON BACKGROUND'
                              : 'NO SAMPLE LOADED · BACKEND OFFLINE',
                  style: const TextStyle(fontSize: 12,
                    fontWeight: FontWeight.w800, color: CareColors.ink),
                ),
                const SizedBox(height: 9),
                const Text('No active preview is not evidence that no fall occurred.',
                  style: TextStyle(color: CareColors.muted, fontSize: 11)),
              ],
            ),
          ),
        ) else ...[
          const StatusPill(
            text: 'VALIDATED FICTIONAL SAMPLE · NOT AUTHENTICATED',
            acknowledged: true,
          ),
          const SizedBox(height: 15),
          Row(children: [
            Expanded(child: _PreviewMetric('SAMPLE ITEMS', '${items.length}')),
            const SizedBox(width: 12),
            Expanded(child: _PreviewMetric('NEEDS REVIEW', '$pending')),
          ]),
          const SizedBox(height: 21),
          SectionHeader('Sample advisories · ${items.length}'),
          const SizedBox(height: 10),
          for (var i = 0; i < items.length; i++)
            Card(
              margin: const EdgeInsets.only(bottom: 10),
              child: InkWell(
                key: Key('preview-select-$i'),
                borderRadius: BorderRadius.circular(20),
                onTap: () => setState(() => _selectedId = items[i].advisoryId),
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Icon(
                      items[i].reviewState == 'pending'
                          ? Icons.assignment_late_outlined
                          : Icons.fact_check_outlined,
                      color: items[i].reviewState == 'pending'
                          ? CareColors.amber : CareColors.teal,
                    ),
                    const SizedBox(width: 12),
                    Expanded(child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(items[i].title, style: const TextStyle(
                          color: CareColors.ink,
                          fontSize: 12, fontWeight: FontWeight.w800,
                        )),
                        const SizedBox(height: 5),
                        Text(items[i].sourceId,
                          style: const TextStyle(color: CareColors.muted, fontSize: 11)),
                        const SizedBox(height: 5),
                        Text(items[i].reviewState == 'pending'
                            ? 'SAMPLE · FOLLOW-UP PENDING'
                            : 'SAMPLE · REVIEWED (NOT VERIFIED)',
                          style: const TextStyle(color: CareColors.muted, fontSize: 10)),
                      ],
                    )),
                    if (selected?.advisoryId == items[i].advisoryId)
                      const Icon(Icons.check_circle_outline, color: CareColors.blue)
                    else
                      const Icon(Icons.chevron_right, color: CareColors.muted),
                  ]),
                ),
              ),
            ),
          if (selected != null) ...[
            const SizedBox(height: 14),
            const SectionHeader('Selected sample · read only'),
            const SizedBox(height: 11),
            Card(
              key: const Key('inbox-selected-detail'),
              margin: EdgeInsets.zero,
              child: Padding(
                padding: const EdgeInsets.all(19),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  const StatusPill(text: 'NO ACTIONS AVAILABLE · DEMO'),
                  const SizedBox(height: 13),
                  Text(selected.title,
                    style: Theme.of(context).textTheme.titleLarge),
                  const SizedBox(height: 15),
                  _PreviewDetail('Source (pseudonymous)', selected.sourceId),
                  _PreviewDetail('Context', selected.context),
                  _PreviewDetail('Provider', selected.meta),
                  // Never imply a real receipt for generated data.
                  const _PreviewDetail('Delivery', 'NOT SENT · fictional data'),
                  _PreviewDetail('Review', 'SAMPLE ONLY · ${selected.reviewState.toUpperCase()}'),
                  const _PreviewDetail('Fall status', 'UNCONFIRMED'),
                  const _PreviewDetail('Emergency dispatch', 'DISABLED'),
                  const SizedBox(height: 4),
                  const Text(
                    'Read-only metadata. Acknowledgement and close actions '
                    'require a future authorized backend and audit log.',
                    style: TextStyle(color: CareColors.muted, fontSize: 11),
                  ),
                ]),
              ),
            ),
          ],
        ],
        const SizedBox(height: 20),
        const Text(
          'This screen never accesses a real caregiver session. '
          'The preview clears after 30 seconds or when the app is backgrounded. '
          'No camera, API, notification, patient record or real receipt is involved.',
          style: TextStyle(color: CareColors.muted, fontSize: 11, height: 1.6),
        ),
      ]),
    );
  }
}

class _PreviewMetric extends StatelessWidget {
  const _PreviewMetric(this.label, this.value);
  final String label, value;
  @override
  Widget build(BuildContext context) => Card(
    margin: EdgeInsets.zero,
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(value, style: const TextStyle(fontSize: 27,
          fontWeight: FontWeight.w900, color: CareColors.ink)),
        Text(label, style: const TextStyle(
          fontSize: 10, fontWeight: FontWeight.w700, color: CareColors.muted)),
      ]),
    ),
  );
}

class _PreviewDetail extends StatelessWidget {
  const _PreviewDetail(this.label, this.value);
  final String label, value;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 13),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label, style: const TextStyle(color: CareColors.muted, fontSize: 11)),
      const SizedBox(height: 3),
      Text(value, style: const TextStyle(
        fontSize: 12, color: CareColors.ink, fontWeight: FontWeight.w700)),
    ]),
  );
}
