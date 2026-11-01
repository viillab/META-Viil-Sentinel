import 'package:flutter/material.dart';
import '../../core/care_theme.dart';
import '../../shared/care_widgets.dart';
import '../incidents/demo_controller.dart';
import '../incidents/demo_incident.dart';

class DemoControlPage extends StatelessWidget {
  const DemoControlPage({
    super.key, required this.controller, required this.onStartWalkthrough,
  });
  final DemoController controller;
  final VoidCallback onStartWalkthrough;

  void _run(BuildContext context, DemoScenario scenario) {
    final event = controller.simulate(scenario);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(event == null
        ? 'Synthetic sitting scenario: no fall candidate generated'
        : 'Fictional event added to Alerts · no notification sent'),
    ));
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Demo control center')),
    body: CenteredPage(children: [
      const DemoNotice(),
      const SizedBox(height: 15),
      SizedBox(
        width: double.infinity,
        child: FilledButton.icon(
          key: const Key('walkthrough-from-controls'),
          onPressed: onStartWalkthrough,
          icon: const Icon(Icons.auto_stories_outlined),
          label: const Text('Start guided demo'),
        ),
      ),
      const SizedBox(height: 20),
      Text('Run a scenario', style: Theme.of(context).textTheme.headlineMedium),
      const SizedBox(height: 7),
      const Text(
        'Generate an invented event and review it in Alerts. '
        'No camera, AI inference, backend request, or push notification.',
        style: TextStyle(color: CareColors.muted, fontSize: 12),
      ),
      const SizedBox(height: 22),
      _ScenarioCard(
        key: const Key('scenario-fall'),
        icon: Icons.personal_injury_outlined,
        title: 'Possible fall candidate',
        subtitle: 'Generated rapid posture change · unconfirmed',
        onTap: () => _run(context, DemoScenario.rapidDescent),
      ),
      _ScenarioCard(
        key: const Key('scenario-transfer'),
        icon: Icons.accessible_forward,
        title: 'Uncertain transfer',
        subtitle: 'Generated follow-up · no confirmed event',
        onTap: () => _run(context, DemoScenario.transfer),
      ),
      _ScenarioCard(
        key: const Key('scenario-sitting'),
        icon: Icons.chair_outlined,
        title: 'Normal sitting',
        subtitle: 'Negative test · creates no candidate',
        onTap: () => _run(context, DemoScenario.sitting),
      ),
      const SizedBox(height: 25),
      const SectionHeader('Environment'),
      const SizedBox(height: 11),
      const Card(
        margin: EdgeInsets.zero,
        child: Padding(
          padding: EdgeInsets.all(19),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _EnvironmentRow('App mode', 'OFFLINE DEMO'),
              _EnvironmentRow('Backend authentication', 'NOT CONNECTED'),
              _EnvironmentRow('Meta provider', 'MOCK ONLY'),
              _EnvironmentRow('Push notifications', 'DISABLED'),
              _EnvironmentRow('Emergency dispatch', 'DISABLED'),
            ],
          ),
        ),
      ),
      const SizedBox(height: 21),
      OutlinedButton.icon(
        key: const Key('reset-demo'),
        onPressed: () {
          controller.reset();
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Demo data reset to its original state')),
          );
        },
        icon: const Icon(Icons.restart_alt),
        label: const Text('Reset demo state'),
      ),
      const SizedBox(height: 10),
      const Text('No account credentials, location, camera feed, private '
        'media or identifiable persons are stored in this demo.',
        style: TextStyle(color: CareColors.muted, fontSize: 11, height: 1.6)),
    ]),
  );
}

class _ScenarioCard extends StatelessWidget {
  const _ScenarioCard({
    super.key, required this.icon, required this.title,
    required this.subtitle, required this.onTap,
  });
  final IconData icon;
  final String title, subtitle;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => Card(
    margin: const EdgeInsets.only(bottom: 12),
    child: InkWell(
      borderRadius: BorderRadius.circular(20),
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Row(children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(0xFFEAF1FF),
              borderRadius: BorderRadius.circular(13),
            ),
            child: Icon(icon, color: CareColors.blue, size: 24),
          ),
          const SizedBox(width: 14),
          Expanded(child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: const TextStyle(
                fontWeight: FontWeight.w800, fontSize: 13,
              )),
              const SizedBox(height: 5),
              Text(subtitle, style: const TextStyle(
                color: CareColors.muted, fontSize: 11,
              )),
            ],
          )),
          const Icon(Icons.play_arrow_rounded, color: CareColors.blue),
        ]),
      ),
    ),
  );
}

class _EnvironmentRow extends StatelessWidget {
  const _EnvironmentRow(this.name, this.value);
  final String name, value;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 8),
    child: Row(children: [
      Expanded(child: Text(name, style: const TextStyle(
        color: CareColors.muted, fontSize: 11,
      ))),
      Flexible(child: Text(value, textAlign: TextAlign.right,
        style: const TextStyle(
          color: CareColors.ink, fontWeight: FontWeight.w800, fontSize: 10,
        ))),
    ]),
  );
}
