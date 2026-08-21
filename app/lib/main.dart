// paws/app/lib/main.dart — PAWS Flutter app
// The rewards + pet-profile app: dog profile → scan receipts → points
// → manufacturer-approved digital coupons (scannable Code 128 barcodes).
import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';

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
    );
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
    final pet = _data!['pet'];
    final health = _data!['health'] as List;
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
        Text('Health & records', style: Theme.of(context).textTheme.titleMedium),
        ...health.map((h) => ListTile(
              leading: Icon(h['kind'] == 'vaccine' ? Icons.vaccines : Icons.medical_services),
              title: Text('${h['name']}'),
              subtitle: Text('${h['kind']} · ${h['date'] ?? ''}'),
            )),
        const SizedBox(height: 8),
        Row(children: [
          Expanded(child: ElevatedButton.icon(
              onPressed: () => _addEvent('vaccine'),
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

  Future<void> _addEvent(String kind) async {
    await http.post(Uri.parse('$API/api/v1/pets/${widget.petId}/events'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'kind': kind, 'name': kind == 'vaccine' ? 'Vaccine' : 'Vet visit', 'date': ''}));
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
