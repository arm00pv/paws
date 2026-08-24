// paws/app/lib/main.dart — PAWS Flutter app
// The rewards + pet-profile app: dog profile → scan receipts → points
// → manufacturer-approved digital coupons (scannable Code 128 barcodes).
import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';
import 'scan_screen.dart';

const API = String.fromEnvironment(
    'PAWS_API', defaultValue: 'http://127.0.0.1:8235');

void main() => runApp(const PawsApp());

class PawsApp extends StatelessWidget {
  const PawsApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'PAWS',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
            seedColor: const Color(0xFFFFB45E), brightness: Brightness.dark),
        useMaterial3: true,
      ),
      home: const HomePage(),
    );
  }
}

String _petAge(String dob) {
  if (dob == null || dob.trim().isEmpty) return 'age unknown';
  try {
    final d = DateTime.parse(dob);
    final now = DateTime.now();
    var yrs = now.year - d.year;
    if (now.month < d.month || (now.month == d.month && now.day < d.day)) yrs--;
    if (yrs < 0) yrs = 0;
    if (yrs == 0) {
      final mos = (now.month - d.month) + (now.year - d.year) * 12;
      if (mos <= 0) return 'baby';
      return '$mos mo';
    }
    return '$yrs yr${yrs == 1 ? '' : 's'}';
  } catch (_) {
    return 'age unknown';
  }
}

String _fmtAge(String dob) => _petAge(dob);

String _birthdayCountdown(String dob) {
  if (dob == null || dob.trim().isEmpty) return '';
  try {
    final d = DateTime.parse(dob);
    final now = DateTime.now();
    var next = DateTime(now.year, d.month, d.day);
    if (next.isBefore(DateTime(now.year, now.month, now.day))) {
      next = DateTime(now.year + 1, d.month, d.day);
    }
    final days = next.difference(DateTime(now.year, now.month, now.day)).inDays;
    return days == 0 ? 'birthday today!' : 'birthday in $days days';
  } catch (_) {
    return '';
  }
}

String _b64(String s) {
  return s;
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});
  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  List<dynamic> _pets = [];
  Map<String, dynamic> _activity = {};
  Map<String, dynamic> _home = {};
  bool _loading = true;
  String? _error;
  int _tab = 0;
  int _carePetId = 0;
  String _carePetName = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await http.get(Uri.parse('$API/api/v1/pets'));
      final a = await http.get(Uri.parse('$API/api/v1/activity'));
      final h = await http.get(Uri.parse('$API/api/v1/home'));
      setState(() {
        _pets = jsonDecode(r.body)['pets'];
        _activity = jsonDecode(a.body);
        _home = jsonDecode(h.body);
        if (_carePetId == 0 && _pets.isNotEmpty) {
          _carePetId = _pets.first['id'];
          _carePetName = '${_pets.first['name']}';
        }
        _loading = false;
        _error = null;
      });
    } catch (e) {
      setState(() { _loading = false; _error = 'Cannot reach PAWS: $e'; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('PAWS — rewards for good boys & girls'),
          actions: [IconButton(icon: const Icon(Icons.refresh), onPressed: _load)]),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.pets_outlined), selectedIcon: Icon(Icons.pets), label: 'Pets'),
          NavigationDestination(icon: Icon(Icons.redeem_outlined), selectedIcon: Icon(Icons.redeem), label: 'Rewards'),
          NavigationDestination(icon: Icon(Icons.insights_outlined), selectedIcon: Icon(Icons.insights), label: 'Activity'),
        ],
      ),
      body: _tab == 1
          ? _petsView()
          : _tab == 2
              ? _rewardsView()
              : _tab == 3
                  ? _activityView()
                  : _homeBody(),
    );
  }

  // ── TAB 1: PETS (the pack) ──────────────────────────────────────────
  Widget _petsView() {
    return _loading
        ? const Center(child: CircularProgressIndicator())
        : ListView(
            padding: const EdgeInsets.all(12),
            children: [
              Text('Your pack',
                  style: Theme.of(context).textTheme.titleLarge
                      ?.copyWith(fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              for (final p in _pets)
                Card(
                  clipBehavior: Clip.antiAlias,
                  child: ListTile(
                    leading: p['photo'] != null && '${p['photo']}'.isNotEmpty
                        ? CircleAvatar(radius: 28, backgroundImage: MemoryImage(base64Decode('${p['photo']}')))
                        : CircleAvatar(radius: 28, backgroundColor: const Color(0xFFFFB45E),
                            child: const Icon(Icons.pets, size: 24, color: Colors.black87)),
                    title: Text('${p['name']}',
                        style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 18)),
                    subtitle: Text([
                      '${p['breed']}',
                      _petAge(p['dob']),
                      if ((p['weight'] ?? 0) > 0) '${p['weight']}kg',
                    ].where((s) => s.isNotEmpty).join(' · ')),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => Navigator.push(context,
                        MaterialPageRoute(builder: (_) => PetPage(petId: p['id']))),
                  ),
                ),
            ],
          );
  }

  // ── TAB 2: REWARDS (the showcase, focused) ──
  Widget _rewardsView() {
    final show = (_home['showcase'] as List? ?? []);
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        Text('Rewards',
            style: Theme.of(context).textTheme.titleLarge
                ?.copyWith(fontWeight: FontWeight.bold)),
        const SizedBox(height: 4),
        Text('${_activity['points'] ?? 0} paw points — claim real pet coupons',
            style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: 8),
        for (final s in show)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  const Icon(Icons.confirmation_number, size: 18),
                  const SizedBox(width: 6),
                  Expanded(child: Text('${s['title']}',
                      style: const TextStyle(fontWeight: FontWeight.w600))),
                  Text('${s['points']} pts',
                      style: TextStyle(fontWeight: FontWeight.bold,
                          color: s['affordable'] == true ? Colors.greenAccent : Colors.grey)),
                ]),
                const SizedBox(height: 6),
                ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value: (s['progress'] ?? 0) / 100.0,
                    minHeight: 8,
                    backgroundColor: Colors.white10,
                    color: s['affordable'] == true ? Colors.greenAccent : const Color(0xFFFFB45E),
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  s['affordable'] == true
                      ? 'Ready to claim!'
                      : '${s['needed'] ?? 0} more pts to unlock',
                  style: Theme.of(context).textTheme.bodySmall),
              ]),
            ),
          ),
        const SizedBox(height: 8),
        Card(
          color: const Color(0x3322B573),
          child: ListTile(
            leading: const Icon(Icons.group_add),
            title: const Text('Refer a friend'),
            subtitle: const Text('+150 pts when they join'),
            trailing: FilledButton(onPressed: _showRefer, child: const Text('Invite')),
          ),
        ),
      ],
    );
  }

  // ── TAB 3: ACTIVITY (the feed, focused) ──
  Widget _activityView() {
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        Text('Recent activity',
            style: Theme.of(context).textTheme.titleLarge
                ?.copyWith(fontWeight: FontWeight.bold)),
        const SizedBox(height: 8),
        for (final r in _activityRows())
          Card(
            child: ListTile(
              leading: const Icon(Icons.receipt_long),
              title: Text('${r['pet']} @ ${r['store']}'),
              subtitle: Text('scan #${r['id']}'),
              trailing: Text('+${(double.tryParse('${r['amount']}') ?? 0).toInt()} pts',
                  style: const TextStyle(fontWeight: FontWeight.w600, color: Colors.greenAccent)),
            ),
          ),
      ],
    );
  }

  // keep the original home body under a renamed method
  Widget _homeBody() {
    return _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text(_error!, textAlign: TextAlign.center))
              : _pets.isEmpty
                  ? _EmptyState(onAdd: () => _showAddPet())
                  : ListView(
                      padding: const EdgeInsets.all(12),
                      children: [
                        // ── THE DASHBOARD (UX review fix: fill the void) ──
                        Card(
                          color: const Color(0x3322B573),
                          child: Padding(
                            padding: const EdgeInsets.all(14),
                            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Text('Your pack',
                                  style: Theme.of(context).textTheme.titleMedium
                                      ?.copyWith(fontWeight: FontWeight.bold)),
                              const SizedBox(height: 4),
                              Text('${_pets.length} fur baby${_pets.length == 1 ? '' : 'ies'} · ${_activity['points'] ?? 0} paw points',
                                  style: Theme.of(context).textTheme.bodySmall
                                      ?.copyWith(color: const Color(0xFFFFD9A0), fontWeight: FontWeight.w600)),
                              if ((_home['pet_stats'] ?? []).isNotEmpty) ...[
                                const SizedBox(height: 8),
                                Wrap(spacing: 6, children: [
                                  for (final ps in (_home['pet_stats'] as List).take(3))
                                    if ((ps['streak'] ?? 0) > 0)
                                      Chip(
                                        avatar: const Icon(Icons.local_fire_department, size: 14, color: Color(0xFFFFB45E)),
                                        label: Text('${ps['name']} · ${ps['streak']}d streak'),
                                        visualDensity: VisualDensity.compact,
                                        backgroundColor: Colors.white10,
                                      ),
                                ]),
                              ],
                              const SizedBox(height: 10),
                              Row(children: [
                                Expanded(child: FilledButton.icon(
                                    onPressed: () => _showAddPet(),
                                    icon: const Icon(Icons.pets), label: const Text('Add a pet'))),
                                const SizedBox(width: 8),
                                Expanded(child: FilledButton.tonalIcon(
                                    onPressed: _showQuickAdd,
                                    icon: const Icon(Icons.camera_alt),
                                    label: const Text('Scan & earn'))),
                              ]),
                            ]),
                          ),
                        ),
                        // ── THE PETS (the emotional anchor — first!) ──
                        for (final p in _pets)
                          Card(
                            clipBehavior: Clip.antiAlias,
                            child: ListTile(
                              leading: p['photo'] != null && '${p['photo']}'.isNotEmpty
                                  ? CircleAvatar(
                                      radius: 28,
                                      backgroundImage: MemoryImage(base64Decode('${p['photo']}')),
                                    )
                                  : CircleAvatar(
                                      radius: 28,
                                      backgroundColor: const Color(0xFFFFB45E),
                                      child: Icon(
                                        (p['species'] == 'cat') ? Icons.pets : Icons.pets,
                                        size: 24, color: Colors.black87,
                                      ),
                                    ),
                              title: Text('${p['name']}',
                                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 18)),
                              subtitle: Text([
                                '${p['breed']}',
                                _petAge(p['dob']),
                                if ('${p['dob']}'.trim().isEmpty) '+ add birthday',
                                if ((p['weight'] ?? 0) > 0) '${p['weight']}kg',
                                if (_birthdayCountdown('${p['dob']}').isNotEmpty)
                                  _birthdayCountdown('${p['dob']}'),
                              ].where((s) => s.isNotEmpty).join(' · ')),
                              trailing: const Icon(Icons.chevron_right),
                              onTap: () => Navigator.push(context,
                                  MaterialPageRoute(builder: (_) => PetPage(petId: p['id']))),
                            ),
                          ),
                        const SizedBox(height: 10),
                        // ── FEATURED REWARD (the void filler — a carousel) ──
                        if ((_home['showcase'] ?? []).isNotEmpty)
                          SizedBox(
                            height: 110,
                            child: ListView(
                              scrollDirection: Axis.horizontal,
                              children: [
                                for (final s in (_home['showcase'] as List).take(5))
                                  Padding(
                                    padding: const EdgeInsets.only(right: 10),
                                    child: SizedBox(
                                      width: 180,
                                      child: Card(
                                        color: s['affordable'] == true
                                            ? const Color(0x3322B573)
                                            : const Color(0x22FFFFFF),
                                        child: Padding(
                                          padding: const EdgeInsets.all(10),
                                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                                            Row(children: [
                                              const Icon(Icons.confirmation_number, size: 14),
                                              const SizedBox(width: 4),
                                              Expanded(child: Text('${s['title']}',
                                                  maxLines: 2, overflow: TextOverflow.ellipsis,
                                                  style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600))),
                                            ]),
                                            const Spacer(),
                                            Text(s['affordable'] == true
                                                ? 'READY TO CLAIM'
                                                : '${s['needed'] ?? 0} pts to go',
                                                style: TextStyle(
                                                    fontSize: 10,
                                                    fontWeight: FontWeight.bold,
                                                    color: s['affordable'] == true
                                                        ? Colors.greenAccent : Colors.grey)),
                                            const SizedBox(height: 2),
                                            ClipRRect(
                                              borderRadius: BorderRadius.circular(3),
                                              child: LinearProgressIndicator(
                                                value: (s['progress'] ?? 0) / 100.0,
                                                minHeight: 5,
                                                backgroundColor: Colors.white10,
                                                color: s['affordable'] == true
                                                    ? Colors.greenAccent : const Color(0xFFFFB45E),
                                              ),
                                            ),
                                          ]),
                                        ),
                                      ),
                                    ),
                                  ),
                              ],
                            ),
                          ),
                        const SizedBox(height: 10),
                        // ── TODAY'S CARE CHECKLIST (the void filler) ──
                        Card(
                          child: Padding(
                            padding: const EdgeInsets.all(12),
                            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Text("Today's care for ${_carePetName}",
                                  style: const TextStyle(fontWeight: FontWeight.bold)),
                              const SizedBox(height: 4),
                              if (_pets.length > 1)
                                Wrap(spacing: 6, children: [
                                  for (final p in _pets)
                                    ChoiceChip(
                                      label: Text('${p['name']}'),
                                      selected: _carePetId == p['id'],
                                      visualDensity: VisualDensity.compact,
                                      onSelected: (_) => setState(() {
                                        _carePetId = p['id'];
                                        _carePetName = '${p['name']}';
                                      }),
                                    ),
                                ]),
                              const SizedBox(height: 6),
                              Wrap(spacing: 8, children: [
                                ActionChip(
                                  avatar: const Icon(Icons.directions_walk, size: 16),
                                  label: const Text('Walk'),
                                  onPressed: () => _quickCheckIn('Walk'),
                                ),
                                ActionChip(
                                  avatar: const Icon(Icons.restaurant, size: 16),
                                  label: const Text('Fed'),
                                  onPressed: () => _quickCheckIn('Fed'),
                                ),
                                ActionChip(
                                  avatar: const Icon(Icons.sports_baseball, size: 16),
                                  label: const Text('Played'),
                                  onPressed: () => _quickCheckIn('Played'),
                                ),
                                ActionChip(
                                  avatar: const Icon(Icons.brush, size: 16),
                                  label: const Text('Brushed'),
                                  onPressed: () => _quickCheckIn('Brushed'),
                                ),
                              ]),
                            ]),
                          ),
                        ),
                        const SizedBox(height: 10),
                        // ── ACTION REQUIRED (care reminders) ──
                        if ((_home['actions'] ?? []).isNotEmpty)
                          Card(
                            color: const Color(0x33E53935),
                            child: Padding(
                              padding: const EdgeInsets.all(12),
                              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                                const Text('Care reminders',
                                    style: TextStyle(fontWeight: FontWeight.bold)),
                                for (final act in (_home['actions'] as List).take(3))
                                  Padding(
                                    padding: const EdgeInsets.symmetric(vertical: 3),
                                    child: Row(children: [
                                      Icon(act['type'] == 'vaccine_overdue'
                                          ? Icons.warning_amber
                                          : act['type'] == 'coupon_ready'
                                              ? Icons.confirmation_number
                                              : Icons.pets,
                                          size: 16,
                                          color: act['type'] == 'vaccine_overdue'
                                              ? Colors.redAccent : null),
                                      const SizedBox(width: 6),
                                      Expanded(child: Text(
                                          '${act['pet']}: ${act['vaccine'] ?? act['about'] ?? ''}'
                                          '${act['due'] != null ? ' (due ${act['due']})' : ''}',
                                          overflow: TextOverflow.ellipsis)),
                                      if (act['type'] == 'vaccine_overdue')
                                        IconButton(
                                          icon: const Icon(Icons.check_circle, size: 18, color: Colors.greenAccent),
                                          tooltip: 'Log shot',
                                          onPressed: () => _logFromHome(act),
                                        ),
                                      if (act['pet_id'] != null)
                                        IconButton(
                                          icon: const Icon(Icons.close, size: 16),
                                          tooltip: 'Dismiss',
                                          onPressed: () => _dismissReminder(act),
                                        ),
                                    ]),
                                  ),
                              ]),
                            ),
                          ),
                        const SizedBox(height: 10),
                        if ((_activity['receipts'] ?? []).isNotEmpty)
                          Card(
                            child: Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                                Text('Recent activity',
                                    style: Theme.of(context).textTheme.labelMedium
                                        ?.copyWith(fontWeight: FontWeight.bold)),
                                for (final r in _activityRows())
                                  Padding(
                                    padding: const EdgeInsets.symmetric(vertical: 3),
                                    child: Row(children: [
                                      const Icon(Icons.receipt_long, size: 16),
                                      const SizedBox(width: 6),
                                      Expanded(child: Text('${r['pet']} @ ${r['store']}',
                                          overflow: TextOverflow.ellipsis)),
                                      Text('+${(double.tryParse('${r['amount']}') ?? 0).toInt()} pts',
                                          style: const TextStyle(fontWeight: FontWeight.w600,
                                              color: Colors.greenAccent)),
                                    ]),
                                  ),
                              ]),
                            ),
                          ),

                      ],
                    );
  }

  Future<void> _showPanel() async {
    final r = await http.get(Uri.parse('$API/api/v1/panel'));
    final d = jsonDecode(r.body);
    if (!mounted) return;
    showDialog(context: context, builder: (ctx) => AlertDialog(
      title: const Text('THE PANEL — pet market intelligence'),
      content: SizedBox(width: 340, child: SingleChildScrollView(child: Column(
          crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
        Text('Panel: ${d['panel']['pets']} pets · \$${d['panel']['spend']} spend'),
        const SizedBox(height: 8),
        const Text('Brand share:', style: TextStyle(fontWeight: FontWeight.bold)),
        for (final b in (d['brand_share'] as List).take(6))
          Text('  ${b['brand']}: ${b['share']}%'),
        const SizedBox(height: 8),
        const Text('Breed × food:', style: TextStyle(fontWeight: FontWeight.bold)),
        for (final m in (d['breed_food_matrix'] as List).take(4))
          Text('  ${m['breed']} ← ${m['brand']}'),
      ]))),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Close'))],
    ));
  }

  Future<void> _showRefer() async {
    if (_pets.isEmpty) return;
    final pid = _pets.first['id'];
    final r = await http.post(Uri.parse('$API/api/v1/pets/$pid/refer'));
    final d = jsonDecode(r.body);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text('Referral code ${d['code']} — +${d['points']} pts when a friend joins')));
  }

  List<dynamic> _activityRows() {
    final seen = <String>{};
    final rows = (_activity['receipts'] as List? ?? [])
        .where((r) => seen.add('${r['pet']}-${r['store']}-${r['amount']}'))
        .toList();
    return rows.take(3).toList();
  }

  Future<void> _quickCheckIn(String what) async {
    if (_pets.isEmpty) return;
    final pid = _carePetId != 0 ? _carePetId : _pets.first['id'];
    await http.post(Uri.parse('$API/api/v1/pets/$pid/checkin'));
    _load();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('$what logged! +25 pts · streak alive 🔥')));
    }
  }

  Future<void> _logFromHome(Map<String, dynamic> act) async {
    final pid = act['pet_id'];
    await http.post(Uri.parse('$API/api/v1/pets/$pid/events'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'kind': 'vaccine', 'name': act['vaccine'] ?? 'Vaccine', 'date': ''}));
    _load();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Logged! Calendar updated.')));
    }
  }

  Future<void> _dismissReminder(Map<String, dynamic> act) async {
    final pid = act['pet_id'];
    final kind = act['type'] == 'vaccine_overdue' ? 'overdue' : 'first_vaccine';
    await http.post(Uri.parse('$API/api/v1/pets/$pid/dismiss'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'kind': kind}));
    _load();
  }

  void _showQuickAdd() {
    if (_pets.isEmpty) return;
    final p = _pets.first;
    Navigator.push(context, MaterialPageRoute(builder: (_) => PetPage(petId: p['id'])));
  }

  void _showAddPet() {
    final name = TextEditingController();
    final breed = TextEditingController();
    final dob = TextEditingController();
    String species = 'dog';
    showDialog(context: context, builder: (ctx) => AlertDialog(
      title: const Text('Add your pet'),
      content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
        TextField(controller: name, decoration: const InputDecoration(labelText: 'Name')),
        TextField(controller: breed, decoration: const InputDecoration(labelText: 'Breed')),
        const SizedBox(height: 8),
        SegmentedButton<String>(
          segments: const [
            ButtonSegment(value: 'dog', icon: Icon(Icons.pets), label: Text('Dog')),
            ButtonSegment(value: 'cat', icon: Icon(Icons.pets), label: Text('Cat')),
          ],
          selected: {species},
          onSelectionChanged: (s) => species = s.first,
        ),
        const SizedBox(height: 8),
        TextField(controller: dob,
            decoration: const InputDecoration(
                labelText: 'Birthday (YYYY-MM-DD)',
                hintText: '2021-04-12',
                helperText: "Tells us your pet's age - so reminders make sense")),
      ])),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
        ElevatedButton(onPressed: () async {
          await http.post(Uri.parse('$API/api/v1/pets'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'name': name.text, 'breed': breed.text,
                              'species': species.toLowerCase(), 'dob': dob.text}));
          if (ctx.mounted) Navigator.pop(ctx);
          _load();
        }, child: const Text('Save (+100 pts)')),
      ],
    ));
  }
}

class _EmptyState extends StatelessWidget {
  final VoidCallback onAdd;
  const _EmptyState({required this.onAdd});
  @override
  Widget build(BuildContext context) => Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.pets, size: 72, color: Colors.grey),
          const SizedBox(height: 12),
          const Text('Add your dog — earn points'),
          const SizedBox(height: 12),
          ElevatedButton(onPressed: onAdd, child: const Text('Add your pet')),
        ]),
      );
}

class PetPage extends StatefulWidget {
  final int petId;
  const PetPage({super.key, required this.petId});
  @override
  State<PetPage> createState() => _PetPageState();
}

class _PetPageState extends State<PetPage> {
  Map<String, dynamic>? _data;
  int _points = 0;
  int _streak = 0;
  List<dynamic> _coupons = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final r = await http.get(Uri.parse('$API/api/v1/pets/${widget.petId}'));
    final d = jsonDecode(r.body);
    final p = await http.get(Uri.parse('$API/api/v1/pets/${widget.petId}/points'));
    final c = await http.get(Uri.parse('$API/api/v1/pets/${widget.petId}/coupons'));
    final s = await http.get(Uri.parse('$API/api/v1/pets/${widget.petId}/streak'));
    setState(() {
      _data = d;
      _points = jsonDecode(p.body)['balance'];
      _coupons = jsonDecode(c.body)['coupons'];
      _streak = jsonDecode(s.body)['streak'];
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_data == null) return const Scaffold(body: Center(child: CircularProgressIndicator()));
    final Map<String, dynamic> d = _data!;
    final pet = d['pet'];
    final health = d['health'] as List;
    final Map<String, dynamic> vcal =
        (d['vaccine_calendar'] is Map)
            ? Map<String, dynamic>.from(d['vaccine_calendar'] as Map)
            : <String, dynamic>{};
    final int overdue = vcal['overdue_count'] ?? 0;
    final List<dynamic> cal = (vcal['calendar'] as List?) ?? const [];
    return Scaffold(
      appBar: AppBar(title: Text('${pet['name']}'),
        actions: [
          IconButton(
            icon: const Icon(Icons.add_a_photo),
            tooltip: 'Add a photo',
            onPressed: () => _uploadPhoto(),
          ),
        ]),
      body: ListView(padding: const EdgeInsets.all(12), children: [
        Card(
          child: Padding(padding: const EdgeInsets.all(16), child: Row(children: [
            const Icon(Icons.emoji_events, size: 40, color: Colors.amber),
            const SizedBox(width: 12),
            Text('$_points points',
                style: Theme.of(context).textTheme.headlineSmall
                    ?.copyWith(fontWeight: FontWeight.bold)),
            const Spacer(),
            ElevatedButton(
                onPressed: _showCatalog, child: const Text('Redeem')),
          ])),
        ),
        // ── THE CARE STREAK (daily engagement hook) ──
        Card(
          color: const Color(0x3322B573),
          child: ListTile(
            leading: const Icon(Icons.local_fire_department, color: Color(0xFFFFB45E)),
            title: Text('$_streak-day care streak',
                style: const TextStyle(fontWeight: FontWeight.bold)),
            subtitle: const Text('Walk, play, brush - tap daily to keep it alive (+25 pts)'),
            trailing: FilledButton(
                onPressed: _checkIn,
                child: const Text("Done today")),
          ),
        ),
        const SizedBox(height: 8),
        // ── THE VACCINE CALENDAR (the sticky feature) ────────────────
        const Text('Vaccine calendar',
            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
        if (overdue > 0)
          Card(
            color: Colors.red.shade900,
            child: ListTile(
              leading: const Icon(Icons.warning_amber, color: Colors.redAccent),
              title: Text('$overdue vaccine(s) OVERDUE — book the vet',
                  style: const TextStyle(fontWeight: FontWeight.bold)),
            ),
          ),
        ...cal.map((c) => Card(
                  margin: const EdgeInsets.symmetric(vertical: 3),
                  child: ListTile(
                    dense: true,
                    leading: Icon(c['overdue'] ? Icons.error : Icons.check_circle,
                        color: c['overdue'] ? Colors.redAccent : Colors.green),
                    title: Text('${c['vaccine']}'),
                    subtitle: Text(c['overdue']
                        ? 'OVERDUE — was due ${c['next']}'
                        : 'next due ${c['next']} (in ${c['days_left']}d)'),
                    trailing: c['overdue']
                        ? FilledButton.tonal(
                            onPressed: () => _addEvent('vaccine', c['protocol']),
                            child: const Text('Log shot'))
                        : null,
                  ),
                )),
        const SizedBox(height: 8),
        Text('Health & records', style: Theme.of(context).textTheme.titleMedium),
        ...health.map((h) => ListTile(
              leading: Icon(h['kind'] == 'vaccine' ? Icons.vaccines : Icons.medical_services),
              title: Text('${h['name']}'),
              subtitle: Text('${h['kind']} · ${h['date'] ?? ''}'),
            )),
        const SizedBox(height: 8),
        Row(children: [
          Expanded(child: ElevatedButton.icon(
              onPressed: _showVaccinePicker,
              icon: const Icon(Icons.vaccines), label: const Text('Log vaccine'))),
          const SizedBox(width: 8),
          Expanded(child: ElevatedButton.icon(
              onPressed: () => _addEvent('vet'),
              icon: const Icon(Icons.medical_services), label: const Text('Log vet visit'))),
        ]),
        const SizedBox(height: 12),
        ElevatedButton.icon(
          onPressed: _scanReceipt,
          icon: const Icon(Icons.document_scanner),
          label: const Text('Scan a receipt (photo → OCR → points)'),
          style: ElevatedButton.styleFrom(backgroundColor: Colors.amber.shade800),
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(child: ElevatedButton.icon(
              onPressed: _scanBarcode,
              icon: const Icon(Icons.qr_code_scanner),
              label: const Text('Scan product'))),
          const SizedBox(width: 8),
          Expanded(child: OutlinedButton.icon(
              onPressed: _showEmailImport,
              icon: const Icon(Icons.email_outlined),
              label: const Text('Add from email'))),
        ]),
        const SizedBox(height: 8),
        Row(children: [
          Expanded(child: OutlinedButton.icon(
              onPressed: _showSpend,
              icon: const Icon(Icons.pie_chart),
              label: const Text('Brand history'))),
        ]),
        const SizedBox(height: 8),
        Row(children: [
          Expanded(child: ElevatedButton.icon(
              onPressed: _logWeight,
              icon: const Icon(Icons.monitor_weight),
              label: const Text('Log weight'))),
          const SizedBox(width: 8),
          Expanded(child: OutlinedButton.icon(
              onPressed: _showDigest,
              icon: const Icon(Icons.insights),
              label: const Text('Pet report'))),
        ]),
        const SizedBox(height: 16),
        const Text('Your coupons', style: TextStyle(fontWeight: FontWeight.bold)),
        ..._coupons.map((c) => ListTile(
              leading: const Icon(Icons.confirmation_number),
              title: Text('${c['title']}'),
              subtitle: Text(c['code']),
              trailing: IconButton(
                icon: const Icon(Icons.qr_code),
                onPressed: () => _showBarcode(c['code']),
              ),
            )),
      ]),
    );
  }

  Future<void> _scanReceipt() async {
    final picker = ImagePicker();
    final XFile? img = await picker.pickImage(source: ImageSource.camera);
    if (img == null) return;
    final bytes = await img.readAsBytes();
    final b64 = base64Encode(bytes);
    // 1. OCR with the local vision model
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Reading the receipt with the vision model…')));
    final ocrResp = await http.post(
        Uri.parse('$API/api/v1/ocr-receipt'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'image_b64': b64}));
    final ocr = jsonDecode(ocrResp.body);
    final text = ocr['text'] ?? '';
    // 2. parse to structured items
    final parseResp = await http.post(
        Uri.parse('$API/api/v1/parse-ocr'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'ocr_text': text}));
    final parsed = jsonDecode(parseResp.body);
    final items = (parsed['items'] as List).cast<Map<String, dynamic>>();
    if (items.isEmpty) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not read the receipt — try a clearer photo')));
      return;
    }
    // 3. confirm with the user, then save
    if (!mounted) return;
    showDialog(context: context, builder: (ctx) => AlertDialog(
      title: Text('Receipt found: ${parsed['store'] ?? ''}'),
      content: SizedBox(width: 300, child: Column(mainAxisSize: MainAxisSize.min, children: [
        for (final it in items)
          ListTile(dense: true,
            title: Text('${it['brand']} ${it['product']}'),
            trailing: Text('\$${it['price']}')),
      ])),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Discard')),
        ElevatedButton(onPressed: () async {
          Navigator.pop(ctx);
          final resp = await http.post(
              Uri.parse('$API/api/v1/receipts'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({
                'pet_id': widget.petId,
                'store': parsed['store'] ?? '',
                'amount': items.fold(0.0, (s, it) => s + (it['price'] as num)),
                'purchases': items,
              }));
          _load();
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(content: Text(respBody(resp.statusCode, resp.body))));
          }
        }, child: const Text('Save + points')),
      ],
    ));
  }

  String respBody(int code, String body) {
    if (code == 200) {
      try {
        final d = jsonDecode(body);
        return 'Receipt saved! +${d['points']} points';
      } catch (_) {}
    }
    return 'Saved';
  }

  Future<void> _checkIn() async {
    await http.post(Uri.parse('$API/api/v1/pets/${widget.petId}/checkin'));
    _load();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Care streak +1! (+25 pts)')));
    }
  }

  Future<void> _uploadPhoto() async {
    final picker = ImagePicker();
    final XFile? img = await picker.pickImage(source: ImageSource.camera);
    if (img == null) return;
    final bytes = await img.readAsBytes();
    final b64 = base64Encode(bytes);
    await http.post(
        Uri.parse('$API/api/v1/pets/${widget.petId}/photo'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'image_b64': b64}));
    _load();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Photo saved — what a cutie!')));
    }
  }

  void _scanBarcode() {
    Navigator.push(context,
        MaterialPageRoute(builder: (_) => ScanScreen(petId: widget.petId)))
        .then((_) => _load());
  }

  Future<void> _logWeight() async {
    final ctrl = TextEditingController();
    showDialog(context: context, builder: (ctx) => AlertDialog(
      title: const Text('Log weight (kg)'),
      content: TextField(
        controller: ctrl,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        decoration: const InputDecoration(
          border: OutlineInputBorder(), hintText: 'e.g. 35.9'),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
        ElevatedButton(onPressed: () async {
          final w = double.tryParse(ctrl.text);
          if (w == null) return;
          await http.post(
              Uri.parse('$API/api/v1/pets/${widget.petId}/weight'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({'weight': w}));
          if (ctx.mounted) Navigator.pop(ctx);
          _load();
        }, child: const Text('Log +50 pts')),
      ],
    ));
  }

  Future<void> _showDigest() async {
    final r = await http.get(Uri.parse('$API/api/v1/pets/${widget.petId}/digest'));
    final d = jsonDecode(r.body);
    if (!mounted) return;
    showDialog(context: context, builder: (ctx) => AlertDialog(
      title: Text(d['pet'].toString() + "'s digest"),
      content: SizedBox(width: 320, child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('Spend: \$${d['spend_total']} (${d['spend_items']} items)'),
        Text('Top brand: ${d['top_brand']}'),
        Text('Points: ${d['points']}'),
        Text('Coupons: ${d['coupons']} (${d['coupons_redeemed']} redeemed)'),
        if (d['last_weight'] != null)
          Text('Weight: ${d['last_weight']}kg (${d['last_weight_date']})'),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Close'))],
    ));
  }

  void _showEmailImport() {
    final ctrl = TextEditingController();
    showDialog(context: context, builder: (ctx) => AlertDialog(
      title: const Text('Import a Chewy/Amazon order email'),
      content: SizedBox(width: 340, child: TextField(
        controller: ctrl,
        maxLines: 8,
        decoration: const InputDecoration(
          border: OutlineInputBorder(),
          hintText: 'Paste the order confirmation email text here…'),
      )),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
        ElevatedButton(onPressed: () async {
          final r = await http.post(
              Uri.parse('$API/api/v1/receipts/email'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({'pet_id': widget.petId, 'email_text': ctrl.text}));
          if (ctx.mounted) Navigator.pop(ctx);
          final d = jsonDecode(r.body);
          if (r.statusCode == 200 && d['ok'] != false) {
            _load();
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                  content: Text('Imported ${d['items'].length} items, +${d['points']} pts')));
            }
          } else {
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text('${d['reason'] ?? 'Import failed'}')));
            }
          }
        }, child: const Text('Import')),
      ],
    ));
  }

  Future<void> _showSpend() async {
    final r = await http.get(Uri.parse('$API/api/v1/pets/${widget.petId}/spend'));
    final d = jsonDecode(r.body);
    if (!mounted) return;
    showDialog(context: context, builder: (ctx) => AlertDialog(
      title: Text(d['pet'].toString() + "'s spend"),
      content: SizedBox(width: 320, child: Column(mainAxisSize: MainAxisSize.min, children: [
        Text('Total: \$${d['total_spend']}', style: const TextStyle(fontWeight: FontWeight.bold)),
        const SizedBox(height: 8),
        for (final b in (d['brands'] as List).take(8))
          ListTile(dense: true,
            title: Text('${b['brand']}'),
            subtitle: Text('${b['items']} items'),
            trailing: Text('\$${b['total']}')),
      ])),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Close'))],
    ));
  }

  void _showVaccinePicker() {
    const vaccines = ['DHPP', 'Rabies', 'Bordetella', 'Leptospirosis',
        'Lyme', 'Heartworm', 'FleaTick'];
    showModalBottomSheet(context: context, builder: (ctx) => ListView(
      children: [
        const ListTile(title: Text('Which vaccine?',
            style: TextStyle(fontWeight: FontWeight.bold))),
        for (final v in vaccines)
          ListTile(
            leading: const Icon(Icons.vaccines),
            title: Text(v),
            onTap: () {
              Navigator.pop(ctx);
              _addEvent('vaccine', v);
            },
          ),
      ],
    ));
  }

  Future<void> _addEvent(String kind, [String? name]) async {
    await http.post(Uri.parse('$API/api/v1/pets/${widget.petId}/events'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'kind': kind, 'name': name ?? (kind == 'vaccine' ? 'Vaccine' : 'Vet visit'), 'date': ''}));
    _load();
  }

  Future<void> _showCatalog() async {
    final r = await http.get(Uri.parse('$API/api/v1/coupons/catalog'));
    final cats = jsonDecode(r.body)['coupons'] as List;
    if (!mounted) return;
    showModalBottomSheet(context: context, builder: (ctx) => ListView(
      children: [
        ListTile(title: Text('Redeem points for coupons', style: TextStyle(fontWeight: FontWeight.bold))),
        for (final c in cats)
          ListTile(
            leading: const Icon(Icons.shopping_bag),
            title: Text('${c['title']}'),
            subtitle: Text('${c['points']} pts'),
            trailing: FilledButton(
              onPressed: () async {
                final resp = await http.post(
                    Uri.parse('$API/api/v1/pets/${widget.petId}/coupons/${c['id']}'));
                if (resp.statusCode == 200) {
                  if (ctx.mounted) Navigator.pop(ctx);
                  _load();
                  if (mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('Coupon minted! Scan the barcode at checkout.')));
                  }
                } else {
                  ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(content: Text('Not enough points (${resp.body})')));
                }
              },
              child: const Text('Claim'),
            ),
          ),
      ],
    ));
  }

  void _showBarcode(Map<String, dynamic> coupon) {
    final code = coupon['code'];
    showDialog(context: context, builder: (ctx) => AlertDialog(
      title: Text('${coupon['title']}'),
      content: Column(mainAxisSize: MainAxisSize.min, children: [
        FutureBuilder<Uint8List>(
          future: http.readBytes(Uri.parse('$API/api/v1/coupons/$code/barcode.png')),
          builder: (c, snap) => snap.hasData
              ? Image.memory(snap.data!, width: 260)
              : const CircularProgressIndicator(),
        ),
        const SizedBox(height: 8),
        Text(code, style: const TextStyle(fontFamily: 'monospace')),
      ]),
      actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Done'))],
    ));
  }
}
