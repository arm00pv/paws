// paws/app/lib/scan_screen.dart — the camera barcode scanner
// Phase 8: point the camera at a product UPC → lookup (panel memory →
// Open Food Facts → teach) → confirm price → points. The panel learns.
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:http/http.dart' as http;

const API = String.fromEnvironment(
    'PAWS_API', defaultValue: 'http://127.0.0.1:8235');

class ScanScreen extends StatefulWidget {
  final int petId;
  const ScanScreen({super.key, required this.petId});
  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  bool _processing = false;

  Future<void> _onBarcode(BarcodeCapture capture) async {
    if (_processing) return;
    final code = capture.barcodes.isNotEmpty
        ? capture.barcodes.first.rawValue
        : null;
    if (code == null || code.isEmpty) return;
    _processing = true;
    // 1. lookup: panel memory → Open Food Facts → unknown
    final lookup = await http
        .get(Uri.parse('$API/api/v1/barcode/${Uri.encodeComponent(code)}'));
    final info = jsonDecode(lookup.body);
    if (!mounted) return;
    if (info['ok'] == true) {
      _askPrice(code, info['brand'] ?? '', info['product'] ?? '');
    } else {
      _askTeach(code);
    }
  }

  /// The UPC is unknown — the user teaches it; the panel never forgets.
  void _askTeach(String upc) {
    final brand = TextEditingController();
    final product = TextEditingController();
    final amount = TextEditingController(text: '0');
    showDialog(context: context, builder: (ctx) => AlertDialog(
      title: const Text('New barcode — teach the panel'),
      content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Text('This UPC is new. Tell us what it is — the panel '
            'never forgets, and every future scan recognizes it.'),
        const SizedBox(height: 8),
        TextField(controller: brand,
            decoration: const InputDecoration(labelText: 'Brand', hintText: 'e.g. Royal Canin')),
        TextField(controller: product,
            decoration: const InputDecoration(labelText: 'Product', hintText: 'e.g. Adult 30kg')),
        TextField(controller: amount,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(labelText: 'Price \$ (optional)')),
      ])),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Skip')),
        ElevatedButton(
          onPressed: () async {
            Navigator.pop(ctx);
            await http.post(
                Uri.parse('$API/api/v1/barcode/$upc/teach'),
                headers: {'Content-Type': 'application/json'},
                body: jsonEncode({'brand': brand.text, 'product': product.text}));
            final amt = double.tryParse(amount.text) ?? 0;
            await _saveReceipt(upc, brand.text, product.text, amt);
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Taught! The panel learned this UPC.')));
              Navigator.pop(context); // close the scanner
            }
          },
          child: const Text('Teach + save')),
      ],
    ));
  }

  /// Known UPC → ask the price, then save the purchase.
  void _askPrice(String upc, String brand, String product) {
    final amount = TextEditingController();
    showDialog(context: context, builder: (ctx) => AlertDialog(
      title: Text('$brand $product'),
      content: TextField(controller: amount,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(labelText: 'Price \$ (optional)')),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Skip')),
        ElevatedButton(onPressed: () async {
          Navigator.pop(ctx);
          await _saveReceipt(upc, brand, product, double.tryParse(amount.text) ?? 0);
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Saved + points')));
          }
        }, child: const Text('Save + points')),
      ],
    ));
  }

  Future<void> _saveReceipt(String upc, String brand, String product,
      double amt) async {
    await http.post(
        Uri.parse('$API/api/v1/receipts/barcode'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'pet_id': widget.petId,
          'upc': upc,
          'brand': brand,
          'product': product,
          'amount': amt,
        }));
    _processing = false;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Scan a pet product')),
      body: Column(children: [
        Expanded(
          child: MobileScanner(
            onDetect: _onBarcode,
            errorBuilder: (context, error) => Center(
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                const Icon(Icons.camera_alt_outlined, size: 48),
                const SizedBox(height: 8),
                const Text('Camera unavailable — enable camera permission'),
                const SizedBox(height: 8),
                Text('$error'),
              ]),
            ),
          ),
        ),
        const Padding(
          padding: EdgeInsets.all(12),
          child: Text('Point the camera at the product barcode (UPC)',
              textAlign: TextAlign.center),
        ),
      ]),
    );
  }
}
