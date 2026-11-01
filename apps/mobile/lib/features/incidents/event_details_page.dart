import 'package:flutter/material.dart';
import '../../core/care_theme.dart';
import '../../shared/care_widgets.dart';
import 'demo_controller.dart';
import 'demo_incident.dart';

class EventDetailsPage extends StatelessWidget {
  const EventDetailsPage({
    super.key, required this.controller, required this.id,
  });
  final DemoController controller;
  final String id;

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: controller,
    builder: (context, _) {
      final event = controller.byId(id);
      if (event == null) {
        return Scaffold(
          appBar: AppBar(title: const Text('Event unavailable')),
          body: const Center(child: Text('This demo event no longer exists.')),
        );
      }
      final pending = event.review == DemoReview.pending;
      return Scaffold(
        appBar: AppBar(title: const Text('Event details')),
        body: CenteredPage(children: [
          const DemoNotice(),
          const SizedBox(height: 20),
          Card(
            margin: EdgeInsets.zero,
            child: Padding(
              padding: const EdgeInsets.all(21),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  StatusPill(
                    text: pending ? 'NEEDS HUMAN FOLLOW-UP' : 'DEMO ACKNOWLEDGED',
                    acknowledged: !pending,
                  ),
                  const SizedBox(height: 17),
                  Text(event.title,
                    style: Theme.of(context).textTheme.headlineSmall),
                  const SizedBox(height: 7),
                  Text('${event.zone} · ${demoTime(event.occurredAt)}',
                    style: const TextStyle(color: CareColors.muted, fontSize: 12)),
                  const Divider(height: 32),
                  _InfoRow('Source', 'Fictional demo scenario'),
                  _InfoRow('Context', event.context),
                  const _InfoRow('Meta AI', 'MOCK ONLY · no provider call'),
                  const _InfoRow('Camera evidence', 'None · no images collected'),
                  const _InfoRow('Notification', 'NOT SENT'),
                  const _InfoRow('Fall confirmation', 'NOT CONFIRMED'),
                ],
              ),
            ),
          ),
          const SizedBox(height: 23),
          const SectionHeader('Event timeline'),
          const SizedBox(height: 12),
          Card(
            margin: EdgeInsets.zero,
            child: Padding(
              padding: const EdgeInsets.all(19),
              child: Column(children: [
                const _TimelineRow(
                  label: 'Synthetic event generated',
                  detail: 'Local scenario · not a sensor observation',
                  active: true,
                ),
                const Divider(height: 24),
                const _TimelineRow(
                  label: 'Human follow-up',
                  detail: 'No assessment or real notification was sent',
                  active: false,
                ),
                const Divider(height: 24),
                _TimelineRow(
                  label: pending ? 'Awaiting demo acknowledgement'
                    : 'Acknowledged in this app session',
                  detail: pending ? 'Choose the action below to continue'
                    : 'Local UI state only · not a server receipt',
                  active: !pending,
                ),
              ]),
            ),
          ),
          const SizedBox(height: 24),
          FilledButton.icon(
            key: const Key('acknowledge-demo'),
            onPressed: pending ? () {
              controller.acknowledge(id);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text(
                  'Demo acknowledged locally · no message sent',
                )),
              );
            } : null,
            icon: Icon(pending ? Icons.check_circle_outline : Icons.done_all),
            label: Text(pending ? 'Acknowledge demo event' : 'Already acknowledged'),
          ),
          const SizedBox(height: 9),
          const Text('Acknowledge is simulated. It does not contact caregivers, '
            'emergency services, or the backend.',
            textAlign: TextAlign.center,
            style: TextStyle(color: CareColors.muted, fontSize: 11)),
        ]),
      );
    },
  );
}

class _InfoRow extends StatelessWidget {
  const _InfoRow(this.label, this.value);
  final String label, value;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 11),
    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      SizedBox(width: 115, child: Text(label,
        style: const TextStyle(color: CareColors.muted, fontSize: 11))),
      Expanded(child: Text(value, style: const TextStyle(
        color: CareColors.ink, fontSize: 11, fontWeight: FontWeight.w700,
      ))),
    ]),
  );
}

class _TimelineRow extends StatelessWidget {
  const _TimelineRow({
    required this.label, required this.detail, required this.active,
  });
  final String label, detail;
  final bool active;
  @override
  Widget build(BuildContext context) => Row(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Icon(active ? Icons.check_circle : Icons.circle_outlined,
        size: 19, color: active ? CareColors.teal : CareColors.muted),
      const SizedBox(width: 13),
      Expanded(child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(
            fontSize: 12, fontWeight: FontWeight.w800,
          )),
          const SizedBox(height: 4),
          Text(detail, style: const TextStyle(
            color: CareColors.muted, fontSize: 11,
          )),
        ],
      )),
    ],
  );
}
