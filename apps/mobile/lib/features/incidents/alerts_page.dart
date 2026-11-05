import 'package:flutter/material.dart';
import '../../core/care_theme.dart';
import '../../shared/care_widgets.dart';
import 'demo_controller.dart';
import 'demo_incident.dart';

class AlertsPage extends StatelessWidget {
  const AlertsPage({
    super.key, required this.controller, required this.onOpenEvent,
  });
  final DemoController controller;
  final void Function(DemoIncident) onOpenEvent;

  @override
  Widget build(BuildContext context) => CenteredPage(children: [
    const DemoNotice(compact: true),
    const SizedBox(height: 22),
    Text('Alerts inbox', style: Theme.of(context).textTheme.headlineMedium),
    const SizedBox(height: 5),
    const Text('Unconfirmed events requiring a person to review.',
      style: TextStyle(color: CareColors.muted, fontSize: 12)),
    const SizedBox(height: 19),
    SectionHeader('Pending review · ${controller.pendingCount}'),
    const SizedBox(height: 12),
    if (controller.pending.isEmpty)
      const Card(child: Padding(
        padding: EdgeInsets.all(24),
        child: Column(children: [
          Icon(Icons.inbox_outlined, size: 36, color: CareColors.teal),
          SizedBox(height: 9),
          Text('No pending demo alerts'),
          SizedBox(height: 6),
          Text('This does not indicate real-world safety.',
            style: TextStyle(fontSize: 11, color: CareColors.muted)),
        ]),
      )),
    for (final incident in controller.pending)
      IncidentTile(incident: incident, onTap: () => onOpenEvent(incident)),
    const SizedBox(height: 12),
    const Text(
      'DEMO ONLY · An Edge candidate is not a confirmed fall. '
      'Meta assessment and delivery receipts are not connected.',
      style: TextStyle(color: CareColors.muted, fontSize: 11, height: 1.6),
    ),
  ]);
}
