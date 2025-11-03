export default function handler(req, res) {
  res.status(200).json({
    ok: true,
    service: 'ribbonline-engine',
    time: new Date().toISOString()
  });
}
