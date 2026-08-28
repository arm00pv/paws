// paws/app/lib/account.dart — the auth session (round 29, reviewer #4)
// The app was "all users are 1" — now: signup/login, token stored, sent
// on every write. Multi-tenant integrity for the panel's per-user data.
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

const API = String.fromEnvironment(
    'PAWS_API', defaultValue: 'http://127.0.0.1:8235');

class Account {
  static String token = '';
  static int userId = 0;
  static String email = '';

  // SEC-5 hardening: the token lives in the OS keychain (flutter_secure_storage),
  // not plaintext shared_preferences — the app is public now
  static const _s = FlutterSecureStorage();

  static bool get loggedIn => token.isNotEmpty;

  static Future<void> load() async {
    token = await _s.read(key: 'paws_token') ?? '';
    userId = int.tryParse(await _s.read(key: 'paws_user_id') ?? '') ?? 0;
    email = await _s.read(key: 'paws_email') ?? '';
  }

  static Future<void> save(String t, int uid, String e) async {
    token = t;
    userId = uid;
    email = e;
    await _s.write(key: 'paws_token', value: t);
    await _s.write(key: 'paws_user_id', value: '$uid');
    await _s.write(key: 'paws_email', value: e);
  }

  static Future<void> clear() async {
    token = '';
    userId = 0;
    email = '';
    await _s.delete(key: 'paws_token');
    await _s.delete(key: 'paws_user_id');
    await _s.delete(key: 'paws_email');
  }

  /// The auth header for write requests.
  static Map<String, String> headers() => {
        'Content-Type': 'application/json',
        if (token.isNotEmpty) 'X-Token': token,
      };
}

/// The signup/login screen — first-run gate for the app.
class AccountScreen extends StatefulWidget {
  final VoidCallback onDone;
  const AccountScreen({super.key, required this.onDone});
  @override
  State<AccountScreen> createState() => _AccountScreenState();
}

class _AccountScreenState extends State<AccountScreen> {
  final email = TextEditingController();
  final token = TextEditingController();
  bool _signup = true;
  bool _busy = false;

  Future<void> _submit() async {
    if (email.text.trim().isEmpty) return;
    setState(() => _busy = true);
    try {
      if (_signup) {
        final r = await http.post(Uri.parse('$API/api/v1/signup'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'email': email.text.trim()}));
        final d = jsonDecode(r.body);
        if (r.statusCode != 200) {
          if (mounted) {
            setState(() => _busy = false);
            ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(content: Text(d['detail'] ?? 'signup failed')));
          }
          return;
        }
        await Account.save(d['token'], d['user_id'], email.text.trim());
        if (mounted) {
          setState(() => _busy = false);
          widget.onDone();
        }
      } else {
        final r = await http.post(Uri.parse('$API/api/v1/login'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'email': email.text.trim(), 'token': token.text.trim()}));
        final d = jsonDecode(r.body);
        if (r.statusCode != 200) {
          if (mounted) {
            setState(() => _busy = false);
            ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Login failed — check your token')));
          }
          return;
        }
        await Account.save(token.text.trim(), d['user_id'], email.text.trim());
        if (mounted) {
          setState(() => _busy = false);
          widget.onDone();
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() => _busy = false);
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Cannot reach PAWS: $e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Your PAWS account')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          const SizedBox(height: 12),
          const Center(child: Icon(Icons.pets, size: 64, color: Color(0xFFFFB45E))),
          const SizedBox(height: 8),
          const Center(child: Text('Sign in to start',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold))),
          const SizedBox(height: 6),
          const Center(child: Text(
              'An account keeps each family\'s pets and data separate — '
              'and powers your rewards across devices.',
              textAlign: TextAlign.center, style: TextStyle(fontSize: 13))),
          const SizedBox(height: 20),
          SegmentedButton<bool>(
            segments: const [
              ButtonSegment(value: true, label: Text('New account')),
              ButtonSegment(value: false, label: Text('I have a token')),
            ],
            selected: {_signup},
            onSelectionChanged: (s) => setState(() => _signup = s.first),
          ),
          const SizedBox(height: 16),
          TextField(controller: email,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(
                  labelText: 'Email', border: OutlineInputBorder())),
          if (!_signup) ...[
            const SizedBox(height: 12),
            TextField(controller: token,
                decoration: const InputDecoration(
                    labelText: 'Your token', border: OutlineInputBorder(),
                    helperText: 'From your other device (Settings → Account)')),
          ],
          const SizedBox(height: 20),
          FilledButton(
            onPressed: _busy ? null : _submit,
            style: FilledButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 16)),
            child: Text(_signup ? 'Create account (+100 pts welcome)' : 'Log in'),
          ),
          const SizedBox(height: 8),
          const Center(child: Text('Free · no card · your data stays yours',
              style: TextStyle(fontSize: 12, color: Colors.grey))),
        ],
      ),
    );
  }
}
