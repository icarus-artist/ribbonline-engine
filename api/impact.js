// /api/impact.js
export default function handler(req, res) {
  const { site = 'test', category = 'safety' } = req.query || {};
  res.status(200).json({
    ok: true,
    site,
    category,
    message: 'RibbonLine Engine API is working correctly.'
  });
}
