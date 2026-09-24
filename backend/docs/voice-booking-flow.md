# Voice booking dialog

Each `VoiceToolExecutor` owns one `VoiceBookingFlow`. Text booking is unchanged.
No new dependency or database schema is required.

## Transitions

| Current state | Event/tool | Next state |
| --- | --- | --- |
| idle | successful `check_availability` | slot-offered |
| slot-offered | `hold_booking_slot` for a returned slot | holding |
| holding | Cal.com acknowledges an unexpired reservation | collecting-name |
| collecting-name | `book_appointment` with name, email and the held date/time | confirming |
| confirming | booking result includes a booking UID | confirmed |
| idle / slot-offered / collecting-name | `booking_recovery(off_script)` | recovery, retaining the previous state |
| recovery | `booking_recovery(resume)` | previous state |
| nonterminal, no operation in flight | explicit cancel / change_slot | release hold, then idle |
| held, no operation in flight | reservation expiry | idle; recheck availability |
| ambiguous calendar failure | any mutating operation | uncertain; human verification required |

`status` inspects the current step. Calls made while a calendar operation is in
flight return its status rather than cancelling it or starting a second operation.
`asyncio.shield` and a retained task let a cancelled tool-response/speech turn finish
the calendar operation. The caller can subsequently recover the completed result.
Confirmed bookings are cached for the call; another booking request cannot create a
second appointment. Cancellation of an already confirmed appointment is deliberately
not part of this dialog.

Holds last five minutes, expire in Cal.com if the call disappears, and use reservation
IDs retained internally, never IDs supplied by the model. The selected staff calendar
is pinned from availability through booking. Changed/inactive staff are rejected.

## Calendar boundary and limits

The adapter uses `POST /v2/slots/reservations` and
`DELETE /v2/slots/reservations/{reservationUid}`, API version `2024-09-04`.
The documented booking API has no reservation UID input. We release our hold just
before the existing conflict-checked booking path. This is **not an atomic reservation
conversion**: another caller can take the slot during that interval. Only an acknowledged
booking UID means confirmed. Voice calendar requests use one attempt to avoid duplicate
writes after an ambiguous response; uncertainty requires human verification.

Dialog state is call-local, not durable across process restarts. Upstream holds expire;
a booking accepted before a process crash must be reconciled through Cal.com/normal
webhook processing. No live provider or phone-call tests are run by the unit suite.

## DTMF navigation

`navigate_booking_menu(transcript, goal)` navigates an **external** IVR using the latest
heard menu. Goals: `book`, `human`, `repeat`, `back`. For example, “Press 1 to book;
press 2 for billing” sends exactly `1`, through the existing DTMF executor.

It reuses the existing IVR parser, requires one unambiguous matching option, excludes
cancellation/rescheduling options when booking, sends no speculative `#` suffix, and
stops on a repeated menu/digit or after eight attempts. A send failure is not retried
automatically. Each next menu requires a new tool call; tones never confirm a booking.
This does not add an inbound keypad receptionist or a Telnyx webhook handler.

The tool is exposed only alongside enabled DTMF tools (including IVR-detection mode).
Holds and hold cancellation inherit the booking approval policy; menu navigation
inherits the DTMF policy. Helpers requiring operator approval are blocked, not queued
for replay after their call has ended. Status/tangent/resume only touch call-local
state and do not require a calendar mutation approval.

## Evidence and verification

Patterns read via the connected Steroids corpus (the standalone `steroids` executable
was unavailable):

- `livekit/agents`, `livekit-agents/livekit/agents/beta/workflows/warm_transfer.py`:
  explicit workflow steps and tracked, interruption-protected operations.
- `livekit/agents`, `examples/telephony/bank-ivr/ivr_navigator_agent.py`:
  separate keypad navigation and conversation behavior.

Cal.com contracts checked on 2026-09-24:

- https://cal.com/docs/api-reference/v2/slots/reserve-a-slot
- https://cal.com/docs/api-reference/v2/slots/delete-a-reserved-slot
- https://cal.com/docs/api-reference/v2/bookings/create-a-booking

Tests exercise the real executor/flow with calendar I/O barriers, cancelled awaiters,
concurrent calls, tangent recovery, expiry, invalid/unoffered input, duplicate booking
prevention, staff-calendar pinning, inherited approval policies, and DTMF loop guards.
HTTP transport fixtures exercise reservation headers/payloads, expiry release, cleanup,
and single-attempt mutation behavior without modifying live calendars.
