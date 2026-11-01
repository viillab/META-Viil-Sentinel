import 'package:flutter/material.dart';
import '../../core/care_theme.dart';
import '../../shared/care_widgets.dart';
import '../incidents/demo_controller.dart';
import '../incidents/demo_incident.dart';

/// A short, fully offline narrated UI sequence for hackathon judges.
/// Only the explicit start action generates a fictional incident.
/// No sensors, Meta, persistence, messaging or backend are invoked.
class DemoWalkthroughPage extends StatefulWidget {
  const DemoWalkthroughPage({
    super.key,
    required this.controller,
    required this.eventId,
    required this.onOpenHistory,
  });

  final DemoController controller;
  final String eventId;
  final VoidCallback onOpenHistory;

  @override
  State<DemoWalkthroughPage> createState() => _DemoWalkthroughPageState();
}

class _DemoWalkthroughPageState extends State<DemoWalkthroughPage> {
  int step = 0;
  static const steps = ['Generate', 'Review', 'Acknowledge', 'History'];

  void nextStep() {
    if (step < 3) setState(() => step++);
  }

  void previousStep() {
    if (step > 0) setState(() => step--);
  }

  void acknowledge() {
    if (widget.controller.acknowledge(widget.eventId)) {
      setState(() => step = 3);
    } else if (widget.controller.byId(widget.eventId)?.review
        == DemoReview.acknowledged) {
      setState(() => step = 3);
    }
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: widget.controller,
    builder: (context, _) {
      final incident = widget.controller.byId(widget.eventId);
      if (incident == null) {
        return Scaffold(
          appBar: AppBar(title: const Text('Guided demo')),
          body: const Center(child: Text('The demo was reset. Start a new walkthrough.')),
        );
      }
      final acknowledged = incident.review == DemoReview.acknowledged;
      return Scaffold(
        appBar: AppBar(
          title: const Text('Guided demo'),
          actions: [
            Padding(
              padding: const EdgeInsets.only(right: 15),
              child: Center(
                child: Text('${step + 1} / 4',
                  style: const TextStyle(
                    color: CareColors.muted,
                    fontWeight: FontWeight.w800,
                  )),
              ),
            ),
          ],
        ),
        body: CenteredPage(children: [
          const DemoNotice(),
          const SizedBox(height: 19),
          Row(
            key: const Key('walkthrough-progress'),
            children: [
              for (var i = 0; i < steps.length; i++) ...[
                if (i != 0) const SizedBox(width: 6),
                Expanded(
                  child: Column(children: [
                    Container(
                      height: 6,
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(20),
                        color: i <= step ? CareColors.blue : CareColors.line,
                      ),
                    ),
                    const SizedBox(height: 8),
                    FittedBox(
                      fit: BoxFit.scaleDown,
                      child: Text(
                        steps[i],
                        style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.w700,
                          color: i == step ? CareColors.blue : CareColors.muted,
                        ),
                      ),
                    ),
                  ]),
                ),
              ],
            ],
          ),
          const SizedBox(height: 25),
          Text(_title(acknowledged),
            style: Theme.of(context).textTheme.headlineMedium),
          const SizedBox(height: 9),
          Text(_description(acknowledged),
            style: const TextStyle(color: CareColors.muted, fontSize: 13)),
          const SizedBox(height: 23),
          Card(
            margin: EdgeInsets.zero,
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: switch (step) {
                0 => _WalkthroughInfo(
                  icon: Icons.psychology_alt_outlined,
                  heading: 'Fictional candidate created',
                  lines: [
                    'Location: ${incident.zone} (sample)',
                    'Source: generated data · not a camera',
                    'Fall status: UNCONFIRMED',
                    'Push delivery: NOT SENT',
                  ],
                ),
                1 => _WalkthroughInfo(
                  icon: Icons.fact_check_outlined,
                  heading: 'Human review is required',
                  lines: [
                    incident.title,
                    'Context: ${incident.context}',
                    'Meta AI: MOCK ONLY · no model call',
                    'Evidence: NONE · no person recorded',
                    'No medical determination or emergency action.',
                  ],
                ),
                2 => _WalkthroughInfo(
                  icon: Icons.how_to_reg_outlined,
                  heading: acknowledged
                      ? 'Already acknowledged in demo'
                      : 'Simulate caregiver acknowledgement',
                  lines: [
                    'This changes local app memory only.',
                    'No delivery receipt, call or notification is sent.',
                    'Event stays unconfirmed after acknowledgement.',
                  ],
                ),
                _ => _WalkthroughInfo(
                  icon: Icons.history_toggle_off_outlined,
                  heading: 'Review trail updated locally',
                  lines: [
                    'State: ${acknowledged ? "DEMO ACKNOWLEDGED" : "REVIEW PENDING"}',
                    'The event is now visible under History.',
                    'Close and reopen the app to reset session memory.',
                    'No backend, patient or emergency system involved.',
                  ],
                ),
              },
            ),
          ),
          const SizedBox(height: 23),
          if (step == 2 && acknowledged)
            const StatusPill(text: 'DEMO ACKNOWLEDGED', acknowledged: true),
          if (step == 3)
            const StatusPill(text: 'LOCAL HISTORY ONLY', acknowledged: true),
          const SizedBox(height: 14),
        ]),
        // Keep the only progression action reachable even on 320px screens
        // with larger accessibility fonts. Details above remain scrollable.
        bottomNavigationBar: SafeArea(
          minimum: const EdgeInsets.fromLTRB(14, 8, 14, 8),
          child: Center(
            heightFactor: 1,
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 680),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      key: Key('walkthrough-primary-$step'),
                      onPressed: switch (step) {
                        0 || 1 => nextStep,
                        2 => acknowledge,
                        _ => widget.onOpenHistory,
                      },
                      icon: Icon(switch (step) {
                        0 => Icons.arrow_forward,
                        1 => Icons.fact_check_outlined,
                        2 => Icons.check_circle_outline,
                        _ => Icons.history,
                      }),
                      label: Text(switch (step) {
                        0 => 'Review simulated candidate',
                        1 => 'Continue to acknowledgement',
                        2 => acknowledged
                            ? 'Show local history' : 'Acknowledge in demo only',
                        _ => 'Open History',
                      }),
                    ),
                  ),
                  if (step > 0)
                    TextButton(
                      key: const Key('walkthrough-back'),
                      onPressed: previousStep,
                      child: const Text('Previous step'),
                    ),
                  const Text(
                    'SIMULATED · No real camera, AI, backend or alerts.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 10, color: CareColors.muted, height: 1.4,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
    },
  );

  String _title(bool acknowledged) => switch (step) {
    0 => 'A candidate appears',
    1 => 'Review before acting',
    2 => 'Acknowledge safely',
    _ => acknowledged ? 'Demo completed' : 'Review pending',
  };

  String _description(bool acknowledged) => switch (step) {
    0 => 'A fictional rapid descent has been added to the sample Alerts inbox.',
    1 => 'Only limited, generated context is available. '
         'No real person has been analyzed.',
    2 => 'Mark the sample as reviewed without contacting anyone.',
    _ => acknowledged
      ? 'The sample is now part of this session\'s local History.'
      : 'The sample was not acknowledged.',
  };
}

class _WalkthroughInfo extends StatelessWidget {
  const _WalkthroughInfo({
    required this.icon, required this.heading, required this.lines,
  });
  final IconData icon;
  final String heading;
  final List<String> lines;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: const Color(0xFFE9F0FE),
          borderRadius: BorderRadius.circular(14),
        ),
        child: Icon(icon, color: CareColors.blue, size: 25),
      ),
      const SizedBox(height: 16),
      Text(heading,
        style: Theme.of(context).textTheme.titleLarge),
      const SizedBox(height: 14),
      for (final line in lines) Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.circle, size: 6, color: CareColors.muted),
            const SizedBox(width: 10),
            Expanded(child: Text(line,
              style: const TextStyle(
                color: CareColors.ink, fontSize: 12, height: 1.45,
              ),
            )),
          ],
        ),
      ),
    ],
  );
}
