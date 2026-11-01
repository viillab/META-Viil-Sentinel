import 'package:flutter/material.dart';
import '../core/care_theme.dart';
import '../features/incidents/demo_incident.dart';

class DemoNotice extends StatelessWidget {
  const DemoNotice({super.key, this.compact = false});
  final bool compact;

  @override
  Widget build(BuildContext context) => Container(
    padding: EdgeInsets.all(compact ? 11 : 14),
    decoration: BoxDecoration(
      color: const Color(0xFFFFF7E9),
      borderRadius: BorderRadius.circular(14),
      border: Border.all(color: const Color(0xFFF1D9AE)),
    ),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Icon(Icons.science_outlined, size: 19, color: Color(0xFF94611F)),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            compact
              ? 'DEMO · SIMULATED DATA ONLY'
              : 'DEMO · SIMULATED DATA ONLY\nNo real monitoring, alerts, Meta AI calls, or emergency response.',
            style: const TextStyle(
              color: Color(0xFF805520), fontSize: 11, fontWeight: FontWeight.w700,
              height: 1.5,
            ),
          ),
        ),
      ],
    ),
  );
}

class SectionHeader extends StatelessWidget {
  const SectionHeader(this.title, {super.key, this.action});
  final String title;
  final Widget? action;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Expanded(child: Text(title, style: Theme.of(context).textTheme.titleLarge)),
      ?action,
    ],
  );
}

class StatusPill extends StatelessWidget {
  const StatusPill({super.key, required this.text, this.acknowledged = false});
  final String text;
  final bool acknowledged;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
    decoration: BoxDecoration(
      color: acknowledged ? const Color(0xFFE6F5F0) : const Color(0xFFFFF1DD),
      borderRadius: BorderRadius.circular(30),
    ),
    child: Text(
      text,
      style: TextStyle(
        color: acknowledged ? const Color(0xFF176B5A) : const Color(0xFF95601D),
        fontSize: 10,
        fontWeight: FontWeight.w800,
        letterSpacing: 0.15,
      ),
    ),
  );
}

String demoTime(DateTime at) {
  final local = at.toLocal();
  String pad(int n) => n.toString().padLeft(2, '0');
  return '${pad(local.day)}/${pad(local.month)} '
    '${pad(local.hour)}:${pad(local.minute)}';
}

class IncidentTile extends StatelessWidget {
  const IncidentTile({super.key, required this.incident, required this.onTap});
  final DemoIncident incident;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Card(
    margin: const EdgeInsets.only(bottom: 10),
    child: InkWell(
      key: Key('incident-${incident.id}'),
      borderRadius: BorderRadius.circular(20),
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.all(17),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.all(11),
              decoration: BoxDecoration(
                color: incident.review == DemoReview.pending
                  ? const Color(0xFFFFF2DF) : const Color(0xFFE8F5F2),
                borderRadius: BorderRadius.circular(13),
              ),
              child: Icon(
                incident.review == DemoReview.pending
                  ? Icons.report_outlined : Icons.check_circle_outline,
                color: incident.review == DemoReview.pending
                  ? CareColors.amber : CareColors.teal, size: 23,
              ),
            ),
            const SizedBox(width: 13),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(incident.title, style: const TextStyle(
                    fontWeight: FontWeight.w800, fontSize: 13,
                  )),
                  const SizedBox(height: 6),
                  Text('${incident.zone} · ${demoTime(incident.occurredAt)}',
                    style: const TextStyle(color: CareColors.muted, fontSize: 11)),
                  const SizedBox(height: 9),
                  StatusPill(
                    text: incident.review == DemoReview.pending
                      ? 'REVIEW NEEDED' : 'DEMO ACKNOWLEDGED',
                    acknowledged: incident.review == DemoReview.acknowledged,
                  ),
                ],
              ),
            ),
            const Icon(Icons.chevron_right, color: CareColors.muted),
          ],
        ),
      ),
    ),
  );
}

class CenteredPage extends StatelessWidget {
  const CenteredPage({super.key, required this.children});
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Center(
    child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 720),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(18, 12, 18, 28),
        children: children,
      ),
    ),
  );
}
