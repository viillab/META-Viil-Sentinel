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
  **Generate → Review → Acknowledge → History**. The first Start action
  creates exactly one fictional rapid-descent event. Reopening an
  unfinished walkthrough **resumes the same pending demo sample** and
  does not inflate the alert count. Acknowledge changes only local
  memory; **Open History** selects the History tab automatically.
  After acknowledgement, **Replay guided scenario** replaces only the
  prior guided sample with a new pending sample. Other manually created
  samples remain untouched. This is an intentional *demo reset*, not a
  persistent audit history. Closing an unfinished walkthrough leaves
  its fictional event pending and never sends a notification. The
  primary action stays pinned at the bottom on small screens; event
  details remain scrollable.
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
To prevent a judge from accidentally growing the in-memory list without
limit, the demo retains at most **32 recent fictional events** and
discards the oldest sample entries first. Reset restores the two seed
events and clears any unfinished guided session.
Live mode is intentionally unavailable pending Member 2's authenticated,
authorized caregiver API and evidence/Meta integration.

## Offline caregiver integration contract sandbox

Go to **Demo control center → Inspect offline Caregiver API contract**.
The integration readiness page displays explicitly blocked Live/Auth/Meta/
Push capabilities. The **Validate generated inbox sample** button
exercises the strict Dart decoder using a freshly generated, fictional
`viil.backend.caregiver_inbox.v1` JSON object. The **Test rejection
of unsafe image field** button verifies that unexpected private-media
metadata is rejected without displaying the input. Neither action sends
a request, changes the local Alerts inbox, authenticates a user, reads
a camera, or makes any assertion of actual notification delivery.
An accepted fictional contract sample is withheld after **30 seconds**
and cleared when the app leaves the foreground. An unsafe-sample test
cancels any previous preview expiry timer without restoring its sample.
These checks remain entirely local and cannot enable Live Mode.

The codec in `lib/features/integration/caregiver_contract_v1.dart`:
- accepts only 4 envelope fields and 13 explicitly named advisory fields;
- enforces 32 KiB max JSON, 30 advisories, UUID and pseudonymous source ID,
  strict UTC timestamp format, duplicate IDs and bounded future event time;
- requires safe enumerated stage/context/provider/delivery/review codes;
- rejects forged delivery receipts, verified-fall/emergency claims, real
  Meta claims attached to simulated evidence, and any extra private fields;
- requires a freshness check (30 seconds / 5-second clock skew) before a
  hypothetical authorized UI could display data, and returns only
  sanitized, mapped presentation labels.

### Read-only Caregiver Inbox Preview

Open **Demo control center → Inspect offline Caregiver API contract →
Open read-only Inbox Preview**. Tap **Load fresh fictional inbox** to
display three synthetic examples: a rapid-descent Edge candidate, an
uncertain wheelchair transfer, and a previously reviewed sample.
Select any sample to inspect only safe, enum-derived context labels,
the explicitly *not sent* notification status, and the absence of
confirmation/emergency dispatch. This preview is independent of the
local Demo Alerts and History and provides **no Acknowledge, Close,
Live, Send, or network operation**.

The fictional inbox snapshot is validated with the same strict codec
as the Contract Sandbox and is **cleared automatically after 30
seconds**, whenever the application leaves the foreground, or when
the preview route closes. **Simulate expired snapshot** verifies that
stale-but-structurally-valid JSON is withheld instead of rendered.
**Load fresh fictional inbox** always creates a new local sample.
The sample is not persisted or treated as an authenticated response.
Tests cover item selection, timeout, fake stale input, background
clear, 320px layouts with larger text, and isolation from the Alerts
queue. No physical Android phone has been accepted yet.

A **literal** `access_scope=authenticated_caregiver` string in sample
JSON is **never proof of authorization**. There is no HTTP adapter and
Live Mode cannot be enabled in this version. Tests additionally verify
that the handoff JSON Schema at
`handoff/team/caregiver_inbox.v1.schema.json` agrees with Dart keys,
limits and enumerations. Schema compatibility is not a substitute for
Member 2's server-side auth, RBAC, tenant isolation and independent
receipt verification.

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
- `lib/features/integration/` — offline read-only caregiver metadata
  validation, sample Inbox Preview, expiry/privacy behavior, readiness
  UI; **no network adapter**
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
- Widget/unit tests cover the end-to-end guided demo, early exit without
  duplicates, replay after acknowledgement, preservation of manual
  scenarios, bounded in-memory retention, and 320px-wide layouts at
  140% text scale. These are simulated tests, not physical Android
  hardware acceptance.
