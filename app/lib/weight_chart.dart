// paws/app/lib/weight_chart.dart — the weight-over-time line chart
// (reviewer #7's point: 'backend already has the data, the app never
// calls it'). A simple CustomPaint chart — no new dependency.
import 'package:flutter/material.dart';

class WeightChart extends StatelessWidget {
  final List<Map<String, dynamic>> curve; // [{weight, date, delta}]
  const WeightChart({super.key, required this.curve});

  @override
  Widget build(BuildContext context) {
    if (curve.length < 2) {
      return const Padding(
        padding: EdgeInsets.all(12),
        child: Text('Log two or more weights to see the trend chart.',
            style: TextStyle(fontSize: 12, color: Colors.grey)),
      );
    }
    final pts = curve.reversed.toList(); // oldest → newest
    final values = pts.map((p) => (p['weight'] ?? 0) as num).toList();
    final minV = values.reduce((a, b) => a < b ? a : b).toDouble();
    final maxV = values.reduce((a, b) => a > b ? a : b).toDouble();
    final range = (maxV - minV).abs() < 0.5 ? 1.0 : (maxV - minV);
    final dates = pts.map((p) => '${p['date']}').toList();

    return Padding(
      padding: const EdgeInsets.all(8),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('Weight trend  ·  ${minV.toStringAsFixed(1)}–${maxV.toStringAsFixed(1)} kg',
            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
        const SizedBox(height: 6),
        SizedBox(
          height: 90,
          width: double.infinity,
          child: CustomPaint(
            painter: _LinePainter(values, minV, range, dates),
          ),
        ),
        const SizedBox(height: 4),
        Text('latest: ${values.last.toStringAsFixed(1)} kg',
            style: const TextStyle(fontSize: 12, color: Colors.greenAccent)),
      ]),
    );
  }
}

class _LinePainter extends CustomPainter {
  final List<num> values;
  final double minV, range;
  final List<String> dates;
  _LinePainter(this.values, this.minV, this.range, this.dates);

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width, h = size.height;
    final pad = 4.0;
    if (values.length < 2) return;
    final step = (w - pad * 2) / (values.length - 1);
    final path = Path();
    for (int i = 0; i < values.length; i++) {
      final x = pad + i * step;
      final y = h - pad - ((values[i].toDouble() - minV) / range) * (h - pad * 2);
      if (i == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }
    // the trend line
    final linePaint = Paint()
      ..color = const Color(0xFFFFB45E)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round;
    canvas.drawPath(path, linePaint);
    // the points + last point highlighted
    for (int i = 0; i < values.length; i++) {
      final x = pad + i * step;
      final y = h - pad - ((values[i].toDouble() - minV) / range) * (h - pad * 2);
      final isLast = i == values.length - 1;
      canvas.drawCircle(
        Offset(x, y),
        isLast ? 4.5 : 2.5,
        Paint()..color = isLast ? Colors.greenAccent : const Color(0xFFFFB45E),
      );
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => true;
}
