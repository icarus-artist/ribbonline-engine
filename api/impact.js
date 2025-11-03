// api/impact.js
export default async function handler(req, res) {
  try {
    const { site, category, compare, force } = req.query;

    if (!site) {
      return res.status(400).json({ ok: false, error: 'Missing site parameter' });
    }

    // (테스트용 더미 응답)
    return res.status(200).json({
      ok: true,
      site,
      category: category || null,
      compare: compare || null,
      force: force || false,
      message: "RibbonLine Engine API is running successfully."
    });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ ok: false, error: 'Internal Server Error' });
  }
}
