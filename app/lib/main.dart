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
            seedColor: const Color(0xFFE07A3F), brightness: Brightness.dark),
        useMaterial3: true,
      ),
      home: const HomePage(),
    );
  }
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});
  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  List<dynamic> _pets = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await http.get(Uri.parse('$API/api/v1/pets'));
      setState(() {
        _pets = jsonDecode(r.body)['pets'];
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
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text(_error!, textAlign: TextAlign.center))
              : _pets.isEmpty
                  ? _EmptyState(onAdd: () => _showAddPet())
                  : ListView(
                      padding: const EdgeInsets.all(12),
                      children: [
                        for (final p in _pets)
                          Card(
                            child: ListTile(
                              leading: CircleAvatar(
                                  child: Text('${p['name']}'[0])),
                              title: Text('${p['name']}'),
                              subtitle: Text(
                                  '${p['breed']} · ${p['weight']}kg · born ${p['dob']}'),
                              trailing: const Icon(Icons.chevron_right),
                              onTap: () => Navigator.push(context,
                                  MaterialPageRoute(builder: (_) => PetPage(petId: p['id']))),
                            ),
                          ),
                      ],
                    ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _showAddPet,
        icon: const Icon(Icons.pets),
        label: const Text('Add a pet'),
      ),
      bottomNavigationBar: BottomAppBar(
        child: Row(mainAxisAlignment: MainAxisAlignment.spaceEvenly, children: [
          TextButton.icon(
              onPressed: _showPanel, icon: const Icon(Icons.bar_chart),
              label: const Text('The Panel')),
          TextButton.icon(
              onPressed: _showRefer, icon: const Icon(Icons.group_add),
              label: const Text('Refer +150')),
        ]),
      ),
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

  void _showAddPet() {
    final name = TextEditingController();
    final breed = TextEditingController();
    showDialog(context: context, builder: (ctx) => AlertDialog(
      title: const Text('Add your pet'),
      content: Column(mainAxisSize: MainAxisSize.min, children: [
        TextField(controller: name, decoration: const InputDecoration(labelText: 'Name')),
        TextField(controller: breed, decoration: const InputDecoration(labelText: 'Breed')),
      ]),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
        ElevatedButton(onPressed: () async {
          await http.post(Uri.parse('$API/api/v1/pets'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'name': name.text, 'breed': breed.text}));
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
    setState(() {
      _data = d;
      _points = jsonDecode(p.body)['balance'];
      _coupons = jsonDecode(c.body)['coupons'];
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
      appBar: AppBar(title: Text('${pet['name']}')),
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
                        ? IconButton(
                            icon: const Icon(Icons.check),
                            onPressed: () => _addEvent('vaccine'),
                            tooltip: 'Log this vaccine')
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
              icon: const Icon(Icons.vaccines), label: const Text('Vaccine +150'))),
          const SizedBox(width: 8),
          Expanded(child: ElevatedButton.icon(
              onPressed: () => _addEvent('vet'),
              icon: const Icon(Icons.medical_services), label: const Text('Vet visit +100'))),
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
              label: const Text('Scan barcode'))),
          const SizedBox(width: 8),
          Expanded(child: OutlinedButton.icon(
              onPressed: _showEmailImport,
              icon: const Icon(Icons.email_outlined),
              label: const Text('Import email'))),
        ]),
        const SizedBox(height: 8),
        Row(children: [
          Expanded(child: OutlinedButton.icon(
              onPressed: _showSpend,
              icon: const Icon(Icons.pie_chart),
              label: const Text('Spend'))),
        ]),
        const SizedBox(height: 8),
        Row(children: [
          Expanded(child: ElevatedButton.icon(
              onPressed: _logWeight,
              icon: const Icon(Icons.monitor_weight),
              label: const Text('Log weight +50'))),
          const SizedBox(width: 8),
          Expanded(child: OutlinedButton.icon(
              onPressed: _showDigest,
              icon: const Icon(Icons.insights),
              label: const Text('Digest'))),
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
              child: const Text('Mint'),
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
