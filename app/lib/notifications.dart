// paws/app/lib/notifications.dart — the reminder engine (reviewer #3)
// Local notifications on Android: vaccine due, flea/tick dose, meal nudge.
// The app schedules from the calendar the backend already computes.
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:timezone/data/latest_all.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

final FlutterLocalNotificationsPlugin _notif =
    FlutterLocalNotificationsPlugin();

Future<void> initNotifications() async {
  tzdata.initializeTimeZones();
  const android = AndroidInitializationSettings('@mipmap/ic_launcher');
  await _notif.initialize(
    settings: const InitializationSettings(android: android),
  );
  // request the permission (Android 13+)
  await _notif
      .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin>()
      ?.requestNotificationsPermission();
}

/// Schedule a one-time reminder at [when] (local time).
Future<void> scheduleReminder({
  required int id,
  required String title,
  required String body,
  required DateTime when,
}) async {
  if (when.isBefore(DateTime.now())) return;
  final local = tz.TZDateTime.from(when, tz.local);
  await _notif.zonedSchedule(
    id: id,
    title: title,
    body: body,
    scheduledDate: local,
    notificationDetails: const NotificationDetails(
      android: AndroidNotificationDetails(
        'paws_reminders',
        'PAWS care reminders',
        channelDescription: 'Vaccine, medication and care reminders',
        importance: Importance.high,
        priority: Priority.high,
      ),
    ),
    androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
  );
}

/// Cancel a scheduled reminder by id.
Future<void> cancelReminder(int id) => _notif.cancel(id: id);

/// Show an immediate notification.
Future<void> showNow(String title, String body) async {
  await _notif.show(
    id: DateTime.now().millisecondsSinceEpoch ~/ 1000 % 100000,
    title: title,
    body: body,
    notificationDetails: const NotificationDetails(
      android: AndroidNotificationDetails(
        'paws_reminders',
        'PAWS care reminders',
        channelDescription: 'Vaccine, medication and care reminders',
        importance: Importance.high,
        priority: Priority.high,
      ),
    ),
  );
}
