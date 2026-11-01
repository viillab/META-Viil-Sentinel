# VIIL-Sentinel Care — Flutter mobile demo

**Status: offline simulated caregiver demo, NOT a real monitoring/medical device.**

This is the Member 1 Flutter application built for the VIIL-Sentinel
hackathon. It is separate from the React Dashboard (`apps/dashboard`)
and does not connect to any backend or external service.

## Demo walkthrough

- Open the app: the Home page shows **DEMO · SIMULATED DATA ONLY**,
  the pending count and recent fictional events.
- For the fastest judge presentation, tap **Start guided demo** from
  Home (or the Demo control center). Four explicit screens lead through
  **Generate → Review → Acknowledge → History**. The Start action creates
  exactly one fictional rapid-descent event. Acknowledge changes only
  local memory; **Open History** selects the History tab automatically.
  Closing the guided screen before acknowledgement leaves the fictional
  event pending and never sends a notification. The primary action stays
  pinned at the bottom on small screens; event details remain scrollable.
- Tap the flask icon → **Demo control center**.
- Tap **Possible fall candidate**, **Uncertain transfer**, or
  **Normal sitting**. The sitting scenario correctly creates no event.
- Go to **Alerts**, select a fictional incident and inspect the
  timeline, mock Meta status, lack of evidence and unconfirmed fall.
- Tap **Acknowledge demo event**. The event moves from Alerts to
  **History**, locally within the running app only.
- Return to Demo control center and **Reset demo state** to repeat.

Nothing is persisted. No camera permissions, API calls, notifications,
media, real patients or emergency dispatch are present. All status
and actions are UI demonstration only. The seed content is fictional.
Live mode is intentionally unavailable pending Member 2's authenticated,
authorized caregiver API and evidence/Meta integration.

## Local prerequisites

- Flutter 3.44.6 / Dart 3.12.2 tested on Windows
- Android SDK to build an Android application
- Chrome (optional) for Flutter Web demo

```powershell
cd D:\VIIL-Sentinel\apps\mobile
flutter pub get
flutter analyze
flutter test
flutter run -d chrome
# or: flutter run -d <authorized-android-device-id>
flutter build apk --debug
```

Flutter uses Material 3 and native `ChangeNotifier` for the demo to
avoid additional packages, secret setup and unnecessary network access.

The local Android **debug-only installable APK** is generated at
`build/app/outputs/flutter-apk/app-debug.apk`. It is debug-signed, not
a production release or a Play Store upload. The GitHub CI job
`flutter-mobile-demo` also publishes the `viil-sentinel-care-demo-debug-apk`
artifact for 7 days when all Flutter validation and builds succeed.

**Thai-locale Android build fix:** Android Gradle ZIP packaging can fail
with `MsDosDateTimeUtils.packDate` / `VerifyException` when a JVM
uses a Buddhist-calendar locale. The project's `android/gradle.properties`
pins `user.language=en` and `user.country=US` **only for its Gradle
daemon**, without changing the Windows language or locale.

## Code layout

- `lib/core/` — app theme and color tokens
- `lib/features/incidents/` — demo event contract, in-memory state,
  Alerts and Event Details
- `lib/features/home/` — status overview
- `lib/features/history/` — acknowledged event history
- `lib/features/demo/` — guided judge walkthrough, controlled fictional
  scenarios and reset
- `lib/shared/` — presentational components

The future `viil.backend.caregiver_inbox.v1` contract is described by
`apps/dashboard/src/caregiverInbox.ts`. It is a frontend proposal and
must not be mistaken for an available authenticated mobile endpoint.
Member 2 owns Backend/Auth/Meta/incident persistence. Mobile code must
not call the unauthenticated `/api/v1/incidents/demo` endpoint as if
it represented real candidate ingestion.

## Privacy and safety

- Event data is generated locally and never leaves memory.
- The main/release Android manifest does not request `INTERNET`. Flutter's
  generated **debug/profile variants do request `INTERNET`** for tooling
  and hot reload; even in debug, app code never makes HTTP requests.
  A production release must independently audit merged permissions.
- No push provider, analytics, cloud SDK or Meta key embedded in app.
- No claims of fall accuracy, real delivery, caregiver receipt or live
  monitoring. All UI is labeled DEMO.
- Human review and real API integration require a separate authorization
  design and security review before enabling Live mode.
- Widget tests cover the end-to-end guided demo, early exit without duplicate
  events, and 320px-wide layouts at 140% text scale. These are simulated
  widget tests, not physical Android hardware acceptance.
