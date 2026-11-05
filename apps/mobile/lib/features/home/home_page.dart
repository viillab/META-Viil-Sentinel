import 'package:flutter/material.dart';
import '../../core/care_theme.dart';
import '../../shared/care_widgets.dart';
import '../incidents/demo_controller.dart';
import '../incidents/demo_incident.dart';

class HomePage extends StatelessWidget {
  const HomePage({
    super.key, required this.controller, required this.onOpenEvent,
    required this.onOpenDemo, required this.onStartWalkthrough,
    required this.onSeeAlerts,
  });
  final DemoController controller;
  final void Function(DemoIncident) onOpenEvent;
  final VoidCallback onOpenDemo;
  final VoidCallback onStartWalkthrough;
  final VoidCallback onSeeAlerts;

  @override
  Widget build(BuildContext context) => CenteredPage(children: [
    const DemoNotice(),
    const SizedBox(height: 15),
    SizedBox(
      width: double.infinity,
      child: FilledButton.icon(
        key: const Key('start-guided-demo'),
        onPressed: onStartWalkthrough,
        icon: const Icon(Icons.auto_stories_outlined),
        label: const Text('Start guided demo'),
      ),
    ),
    const SizedBox(height: 24),
    Text('Care at a glance', style: Theme.of(context).textTheme.headlineMedium),
    const SizedBox(height: 5),
    const Text('A calm overview for human-supervised follow-up.',
      style: TextStyle(color: CareColors.muted, fontSize: 12)),
    const SizedBox(height: 20),
    Container(
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFF102A4C), Color(0xFF254A85)],
          begin: Alignment.topLeft, end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(24),
      ),
      padding: const EdgeInsets.all(23),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const Icon(Icons.shield_outlined, color: Color(0xFFABCEF9)),
            const SizedBox(width: 9),
            const Expanded(child: Text('DEMO MONITORING OVERVIEW',
              style: TextStyle(color: Color(0xFFC3D9F7), fontSize: 11,
                fontWeight: FontWeight.w800, letterSpacing: 0.8))),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
              decoration: BoxDecoration(
                color: const Color(0xFF415D82), borderRadius: BorderRadius.circular(12),
              ),
              child: const Text('OFFLINE', style: TextStyle(
                color: Colors.white, fontSize: 9, fontWeight: FontWeight.w900)),
            ),
          ]),
          const SizedBox(height: 26),
          Row(children: [
            Expanded(child: _HeroMetric(
              key: const Key('pending-count'),
              value: '${controller.pendingCount}', label: 'Needs review',
            )),
            Container(width: 1, height: 63, color: const Color(0xFF527096)),
            const SizedBox(width: 20),
            Expanded(child: _HeroMetric(
              value: '${controller.reviewedCount}', label: 'Acknowledged',
            )),
          ]),
          const SizedBox(height: 20),
          const Text('No devices connected · No real alerts sent',
            style: TextStyle(color: Color(0xFFB2C8E6), fontSize: 11)),
        ],
      ),
    ),
    const SizedBox(height: 25),
    SectionHeader('Quick actions', action: TextButton(
      onPressed: onOpenDemo, child: const Text('Demo controls'),
    )),
    const SizedBox(height: 11),
    Row(children: [
      Expanded(child: _QuickAction(
        key: const Key('quick-scenario'),
        label: 'Run a scenario',
        icon: Icons.play_circle_outline,
        onTap: onOpenDemo,
      )),
      const SizedBox(width: 11),
      Expanded(child: _QuickAction(
        label: 'Review alerts',
        icon: Icons.fact_check_outlined,
        onTap: onSeeAlerts,
      )),
    ]),
    const SizedBox(height: 26),
    SectionHeader('Recent demo activity', action: TextButton(
      onPressed: onSeeAlerts, child: const Text('View all'),
    )),
    const SizedBox(height: 10),
    for (final incident in controller.events.take(3))
      IncidentTile(incident: incident, onTap: () => onOpenEvent(incident)),
    const SizedBox(height: 5),
    const Text('All displayed events are fictional and exist in memory only.',
      style: TextStyle(color: CareColors.muted, fontSize: 11)),
  ]);
}

class _HeroMetric extends StatelessWidget {
  const _HeroMetric({super.key, required this.value, required this.label});
  final String value, label;
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(value, style: const TextStyle(
        color: Colors.white, fontSize: 38,
        fontWeight: FontWeight.w900, letterSpacing: -1.2,
      )),
      Text(label, style: const TextStyle(
        color: Color(0xFFD1DEF2), fontSize: 11, fontWeight: FontWeight.w600,
      )),
    ],
  );
}

class _QuickAction extends StatelessWidget {
  const _QuickAction({
    super.key, required this.label, required this.icon, required this.onTap,
  });
  final String label;
  final IconData icon;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => Card(
    margin: EdgeInsets.zero,
    child: InkWell(
      borderRadius: BorderRadius.circular(20),
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(15, 21, 12, 21),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: CareColors.blue, size: 26),
            const SizedBox(height: 17),
            Text(label, style: const TextStyle(
              color: CareColors.ink, fontSize: 12, fontWeight: FontWeight.w800,
            )),
          ],
        ),
      ),
    ),
  );
}
