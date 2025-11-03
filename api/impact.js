export default async function handler(req, res) {
  const { site = 'test', category = '' } = req.query || {};
  // 최소 동작 확인용
  res.status(200).json({ ok: true, site, category, engine: 'vercel-node' });
}
