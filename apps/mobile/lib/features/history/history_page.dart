import 'package:flutter/material.dart';
import '../../core/care_theme.dart';
import '../../shared/care_widgets.dart';
import '../incidents/demo_controller.dart';
import '../incidents/demo_incident.dart';

class HistoryPage extends StatelessWidget {
  const HistoryPage({
    super.key, required this.controller, required this.onOpenEvent,
  });
  final DemoController controller;
  final void Function(DemoIncident) onOpenEvent;

  @override
  Widget build(BuildContext context) => CenteredPage(children: [
    const DemoNotice(compact: true),
    const SizedBox(height: 22),
    Text('Activity history', style: Theme.of(context).textTheme.headlineMedium),
    const SizedBox(height: 5),
    const Text('Local acknowledgements from this demo session only.',
      style: TextStyle(color: CareColors.muted, fontSize: 12)),
    const SizedBox(height: 20),
    SectionHeader('Acknowledged · ${controller.reviewedCount}'),
    const SizedBox(height: 11),
    if (controller.acknowledged.isEmpty)
      const Card(child: Padding(
        padding: EdgeInsets.all(24),
        child: Text('Nothing acknowledged yet.',
          style: TextStyle(color: CareColors.muted)),
      )),
    for (final incident in controller.acknowledged)
      IncidentTile(incident: incident, onTap: () => onOpenEvent(incident)),
    const SizedBox(height: 15),
    const Text('History is not persisted. Closing the application resets it.',
      style: TextStyle(color: CareColors.muted, fontSize: 11)),
  ]);
}
