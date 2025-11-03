export default function handler(req, res) {
  const { site = 'test', category = '' } = req.query || {};
  res.status(200).json({ ok: true, site, category, engine: 'vercel-node' });
}
