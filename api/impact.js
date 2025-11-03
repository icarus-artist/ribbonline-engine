// api/impact.js
export default function handler(req, res) {
  const { site, category, compare, force } = req.query;

  res.status(200).json({
    ok: true,
    message: "RibbonLine Engine API",
    params: { site, category, compare, force },
    time: new Date().toISOString(),
  });
}
