import 'package:flutter/material.dart';
import '../core/care_theme.dart';
import '../features/incidents/demo_controller.dart';
import '../features/incidents/demo_incident.dart';
import '../features/home/home_page.dart';
import '../features/incidents/alerts_page.dart';
import '../features/incidents/event_details_page.dart';
import '../features/history/history_page.dart';
import '../features/demo/demo_control_page.dart';
import '../features/demo/demo_walkthrough_page.dart';

class CareApp extends StatefulWidget {
  const CareApp({super.key});

  @override
  State<CareApp> createState() => _CareAppState();
}

class _CareAppState extends State<CareApp> {
  late final DemoController controller = DemoController();
  final GlobalKey<NavigatorState> navigatorKey = GlobalKey<NavigatorState>();
  int tab = 0;

  void openEvent(DemoIncident event) {
    navigatorKey.currentState!.push(MaterialPageRoute<void>(
      builder: (_) => EventDetailsPage(controller: controller, id: event.id),
    ));
  }

  void startGuidedDemo({bool replayCurrent = false}) {
    final event = controller.startOrResumeGuidedDemo();
    final route = MaterialPageRoute<void>(
      builder: (_) => DemoWalkthroughPage(
        controller: controller,
        eventId: event.id,
        onReplay: () => startGuidedDemo(replayCurrent: true),
        onOpenHistory: () {
          navigatorKey.currentState!.pop();
          setState(() => tab = 2);
        },
      ),
    );
    if (replayCurrent) {
      navigatorKey.currentState!.pushReplacement(route);
    } else {
      navigatorKey.currentState!.push(route);
    }
  }

  void openDemo() {
    navigatorKey.currentState!.push(MaterialPageRoute<void>(
      builder: (_) => DemoControlPage(
        controller: controller,
        onStartWalkthrough: () {
          navigatorKey.currentState!.pop();
          startGuidedDemo();
        },
      ),
    ));
  }

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    debugShowCheckedModeBanner: false,
    title: 'VIIL Sentinel Care · Demo',
    theme: buildCareTheme(),
    navigatorKey: navigatorKey,
    home: Scaffold(
      appBar: AppBar(
        toolbarHeight: 72,
        titleSpacing: 20,
        title: const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('VIIL  /  SENTINEL', style: TextStyle(
              color: CareColors.ink, fontSize: 14, fontWeight: FontWeight.w900,
              letterSpacing: 1.0,
            )),
            SizedBox(height: 3),
            Text('CAREGIVER DEMO', style: TextStyle(
              color: CareColors.muted, fontSize: 10, fontWeight: FontWeight.w700,
              letterSpacing: 1.5,
            )),
          ],
        ),
        actions: [
          IconButton(
            key: const Key('open-demo-controls'),
            tooltip: 'Open demo controls',
            onPressed: openDemo,
            icon: const Icon(Icons.science_outlined, color: CareColors.blue),
          ),
          const SizedBox(width: 9),
        ],
      ),
      body: ListenableBuilder(
        listenable: controller,
        builder: (context, _) {
          final Widget page = switch (tab) {
            0 => HomePage(
              controller: controller,
              onOpenEvent: openEvent,
              onOpenDemo: openDemo,
              onStartWalkthrough: startGuidedDemo,
              onSeeAlerts: () => setState(() => tab = 1),
            ),
            1 => AlertsPage(controller: controller, onOpenEvent: openEvent),
            _ => HistoryPage(controller: controller, onOpenEvent: openEvent),
          };
          return KeyedSubtree(key: ValueKey(tab), child: page);
        },
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: tab,
        onDestinationSelected: (index) => setState(() => tab = index),
        destinations: const [
          NavigationDestination(
            key: Key('tab-home'),
            icon: Icon(Icons.space_dashboard_outlined),
            selectedIcon: Icon(Icons.space_dashboard_rounded),
            label: 'Home',
          ),
          NavigationDestination(
            key: Key('tab-alerts'),
            icon: Icon(Icons.notifications_none_outlined),
            selectedIcon: Icon(Icons.notifications_active_outlined),
            label: 'Alerts',
          ),
          NavigationDestination(
            key: Key('tab-history'),
            icon: Icon(Icons.history_outlined),
            selectedIcon: Icon(Icons.history_rounded),
            label: 'History',
          ),
        ],
      ),
    ),
  );
}
